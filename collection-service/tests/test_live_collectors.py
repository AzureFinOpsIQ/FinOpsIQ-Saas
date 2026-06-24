from __future__ import annotations

import sys
import types
from datetime import datetime, timezone
from types import SimpleNamespace

from shared_lib.domain.context import OperationContext
from src.collector.advisor_collector import AdvisorCollector
from src.collector.aks_collector import AksCollector
from src.collector.cost_collector import CostCollector
from src.collector.metrics_collector import MetricsCollector
from src.collector.resource_graph_collector import ResourceGraphCollector


def put_module(monkeypatch, name: str, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    monkeypatch.setitem(sys.modules, name, module)
    return module


def context():
    return OperationContext.create("tenant-a", "sub-a")


def test_cost_collector_maps_live_cost_management_rows(test_settings, monkeypatch):
    class AnyModel:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class CostManagementClient:
        def __init__(self, credential):
            self.query = SimpleNamespace(
                usage=lambda scope, parameters: SimpleNamespace(
                    columns=[
                        SimpleNamespace(name="UsageDate"),
                        SimpleNamespace(name="PreTaxCost"),
                        SimpleNamespace(name="UsageQuantity"),
                        SimpleNamespace(name="ResourceId"),
                        SimpleNamespace(name="ResourceGroup"),
                        SimpleNamespace(name="ServiceName"),
                        SimpleNamespace(name="ResourceLocation"),
                        SimpleNamespace(name="Currency"),
                    ],
                    rows=[
                        [
                            "20260624",
                            12.5,
                            4,
                            "/subscriptions/sub-a/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-a",
                            "rg",
                            "Virtual Machines",
                            "eastus",
                            "INR",
                        ]
                    ],
                )
            )

    put_module(monkeypatch, "azure.mgmt.costmanagement", CostManagementClient=CostManagementClient)
    put_module(
        monkeypatch,
        "azure.mgmt.costmanagement.models",
        QueryDefinition=AnyModel,
        QueryDataset=AnyModel,
        QueryAggregation=AnyModel,
        QueryGrouping=AnyModel,
        QueryTimePeriod=AnyModel,
    )

    payload = CostCollector(test_settings, context(), credential="cred")._fetch_live_data()

    assert payload["metadata"]["source"] == "live"
    assert payload["records"][0]["date"] == "2026-06-24"
    assert payload["records"][0]["costAmount"] == 12.5


def test_metrics_collector_maps_vm_metrics_and_ignores_metric_errors(test_settings, monkeypatch):
    vm = SimpleNamespace(
        id="/subscriptions/sub-a/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-a",
        name="vm-a",
        location="eastus",
        hardware_profile=SimpleNamespace(vm_size="Standard_B2s"),
    )

    class ComputeManagementClient:
        def __init__(self, credential, subscription_id):
            self.virtual_machines = SimpleNamespace(list_all=lambda: [vm])

    class MonitorManagementClient:
        def __init__(self, credential, subscription_id):
            self.metric_definitions = SimpleNamespace(
                list=lambda resource_id: [
                    SimpleNamespace(name=SimpleNamespace(value="Percentage CPU")),
                    SimpleNamespace(name=SimpleNamespace(value="Available Memory Bytes")),
                ]
            )
            self.metrics = SimpleNamespace(list=self.list_metrics)

        def list_metrics(self, resource_id, **kwargs):
            average = 5.0 if kwargs["metricnames"] == "Percentage CPU" else 750_000_000.0
            point = SimpleNamespace(average=average)
            metric = SimpleNamespace(
                name=SimpleNamespace(value=kwargs["metricnames"]),
                unit="Percent",
                timeseries=[SimpleNamespace(data=[point])],
            )
            return SimpleNamespace(value=[metric])

    put_module(monkeypatch, "azure.mgmt.compute", ComputeManagementClient=ComputeManagementClient)
    put_module(monkeypatch, "azure.mgmt.monitor", MonitorManagementClient=MonitorManagementClient)

    payload = MetricsCollector(test_settings, context(), credential="cred")._fetch_live_data()

    assert payload["resources"][0]["resourceName"] == "vm-a"
    assert payload["resources"][0]["metrics"]["Percentage CPU"]["average"] == 5.0
    now = datetime.now(timezone.utc)
    assert MetricsCollector._query_metrics(SimpleNamespace(metrics=SimpleNamespace(list=lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("skip")))), "id", ["Bad"], now, now) == {}


def test_resource_graph_collector_maps_live_inventory_cost_estimates(test_settings, monkeypatch):
    class QueryRequest:
        def __init__(self, **kwargs):
            self.query = kwargs["query"]

    class ResourceGraphClient:
        def __init__(self, credential):
            pass

        def resources(self, request):
            query = request.query.lower()
            if "microsoft.compute/disks" in query:
                return SimpleNamespace(data=[{"diskId": "disk-a", "diskSizeGb": 100}])
            if "publicipaddresses" in query:
                return SimpleNamespace(data=[{"name": "pip-a", "associated": False}])
            return SimpleNamespace(data=[{"name": "vm-a", "type": "microsoft.compute/virtualmachines"}])

    put_module(monkeypatch, "azure.mgmt.resourcegraph", ResourceGraphClient=ResourceGraphClient)
    put_module(monkeypatch, "azure.mgmt.resourcegraph.models", QueryRequest=QueryRequest)

    payload = ResourceGraphCollector(test_settings, context(), credential="cred")._fetch_live_data()
    enriched = ResourceGraphCollector(test_settings, context(), credential="cred")._simulate_api_ingestion(payload, is_live=True)

    assert payload["unattachedDisks"][0]["monthlyCostEstimateUsd"] == 15.0
    assert payload["publicIps"][0]["monthlyCostEstimateUsd"] == 3.65
    assert enriched["summary"]["totalOrphanedCostEstimateUsd"] == 18.65


def test_advisor_collector_filters_cost_recommendations_and_summarizes(test_settings, monkeypatch):
    rec = SimpleNamespace(
        category=SimpleNamespace(value="Cost"),
        resource_metadata=SimpleNamespace(
            resource_id="/subscriptions/sub-a/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-a"
        ),
        extended_properties={"savingsAmount": "42.5"},
        id="/subscriptions/sub-a/providers/Microsoft.Advisor/recommendations/rec-a",
        impact=SimpleNamespace(value="High"),
        impacted_field="Microsoft.Compute/virtualMachines",
        short_description=SimpleNamespace(problem="Oversized", solution="Resize"),
        impacted_value="vm-a",
        last_updated=None,
    )
    ignored = SimpleNamespace(category="Security")

    class AdvisorManagementClient:
        def __init__(self, credential, subscription_id):
            self.recommendations = SimpleNamespace(list=lambda: [rec, ignored])

    put_module(monkeypatch, "azure.mgmt.advisor", AdvisorManagementClient=AdvisorManagementClient)

    collector = AdvisorCollector(test_settings, context(), credential="cred")
    payload = collector._fetch_live_data()
    collector._apply_ingestion_transforms(payload)

    assert len(payload["recommendations"]) == 1
    assert payload["recommendations"][0]["monthlySavingsUsd"] == 42.5
    assert payload["summary"]["highImpact"] == 1


def test_aks_collector_maps_cluster_node_pool_metrics(test_settings, monkeypatch):
    cluster = SimpleNamespace(
        id="/subscriptions/sub-a/resourceGroups/rg/providers/Microsoft.ContainerService/managedClusters/aks-a",
        name="aks-a",
        location="eastus",
        kubernetes_version="1.30",
        agent_pool_profiles=[SimpleNamespace(name="system", vm_size="Standard_D2s_v5", count=2)],
    )

    class ContainerServiceClient:
        def __init__(self, credential, subscription_id):
            self.managed_clusters = SimpleNamespace(list=lambda: [cluster])

    class MonitorManagementClient:
        def __init__(self, credential, subscription_id):
            self.metric_definitions = SimpleNamespace(
                list=lambda resource_id: [
                    SimpleNamespace(name=SimpleNamespace(value="node_cpu_usage_percentage")),
                    SimpleNamespace(name=SimpleNamespace(value="node_memory_working_set_percentage")),
                ]
            )
            self.metrics = SimpleNamespace(
                list=lambda resource_id, **kwargs: SimpleNamespace(
                    value=[
                        SimpleNamespace(
                            name=SimpleNamespace(value=kwargs["metricnames"]),
                            unit="Percent",
                            timeseries=[SimpleNamespace(data=[SimpleNamespace(average=12.0)])],
                        )
                    ]
                )
            )

    put_module(monkeypatch, "azure.mgmt.containerservice", ContainerServiceClient=ContainerServiceClient)
    put_module(monkeypatch, "azure.mgmt.monitor", MonitorManagementClient=MonitorManagementClient)

    collector = AksCollector(test_settings, context(), credential="cred")
    payload = collector._fetch_live_data()
    collector._apply_ingestion_transforms(payload)

    assert payload["clusters"][0]["clusterName"] == "aks-a"
    assert payload["clusters"][0]["nodePools"][0]["nodeCount"] == 2
    assert payload["summary"]["underutilizedClusters"] == 1
