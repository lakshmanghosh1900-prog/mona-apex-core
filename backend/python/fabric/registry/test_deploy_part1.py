import pytest

CANONICAL_SPEC = "MONA - Powered by Apex Core"


# ---------- Stage 7.1 - Deployment Manager (14) ----------


def test_deployment_manager_exists():
    from fabric.registry.deployment_manager import get_deployment_manager

    dm = get_deployment_manager()
    assert dm is not None
    assert get_deployment_manager() is dm


def test_deploy_success():
    from fabric.registry.deployment_manager import get_deployment_manager

    dm = get_deployment_manager()
    r = dm.deploy("7.1.0-test", env="test", actor="tester")
    assert r["success"] == True
    assert r["version"] == "7.1.0-test"
    assert r["deployment"]["status"] == "DEPLOYED"


def test_deploy_invalid_version():
    from fabric.registry.deployment_manager import get_deployment_manager

    dm = get_deployment_manager()
    r = dm.deploy("", env="test", actor="tester")
    assert r["success"] == False
    assert r["canonical_spec"] == CANONICAL_SPEC


def test_health_probe():
    from fabric.registry.deployment_manager import get_deployment_manager

    dm = get_deployment_manager()
    r = dm.health_probe("api")
    assert "healthy" in r
    assert "checks" in r
    assert "api_gateway" in r["checks"]
    assert "enterprise_audit" in r["checks"]
    assert r["total"] == len(r["checks"])


def test_health_probe_all_ok():
    from fabric.registry.deployment_manager import get_deployment_manager

    dm = get_deployment_manager()
    r = dm.health_probe("api")
    assert r["all_checks"] == True
    assert r["healthy"] == True
    assert all(r["checks"].values())


def test_get_deployments():
    from fabric.registry.deployment_manager import get_deployment_manager

    dm = get_deployment_manager()
    dm.deploy("7.1.0-count", env="staging", actor="tester")
    r = dm.get_deployments()
    assert r["count"] >= 1
    assert r["canonical_spec"] == CANONICAL_SPEC


def test_health_history():
    from fabric.registry.deployment_manager import get_deployment_manager

    dm = get_deployment_manager()
    dm.health_probe("api")
    r = dm.get_health_history()
    assert r["count"] >= 1
    assert r["checks"][-1]["component"] == "api"


def test_deploy_env_field():
    from fabric.registry.deployment_manager import get_deployment_manager

    dm = get_deployment_manager()
    r = dm.deploy("7.1.0-env", env="staging", actor="tester")
    assert r["env"] == "staging"
    assert r["deployment"]["env"] == "staging"


def test_canonical_spec_deploy():
    from fabric.registry.deployment_manager import get_deployment_manager

    dm = get_deployment_manager()
    r = dm.deploy("7.1.0-canonical", env="test", actor="tester")
    assert r["canonical_spec"] == CANONICAL_SPEC
    assert dm.get_stats()["canonical_spec"] == CANONICAL_SPEC
    assert dm.get_deployments()["canonical_spec"] == CANONICAL_SPEC


def test_zero_cost_isolated_deploy():
    from fabric.registry.deployment_manager import get_deployment_manager

    dm = get_deployment_manager()
    r = dm.deploy("7.1.0-zero", env="test", actor="tester")
    assert r["zero_cost"] == True
    assert r["isolated"] == True
    assert dm.get_stats()["zero_cost"] == True


def test_stats_total_deployments():
    from fabric.registry.deployment_manager import get_deployment_manager

    dm = get_deployment_manager()
    before = dm.get_stats()["total_deployments"]
    dm.deploy("7.1.0-stats", env="test", actor="tester")
    after = dm.get_stats()["total_deployments"]
    assert after == before + 1
    assert dm.get_stats()["total_health_checks"] >= 1


def test_stats_wired_deploy():
    from fabric.registry.deployment_manager import get_deployment_manager

    dm = get_deployment_manager()
    s = dm.get_stats()
    assert "wired" in s
    assert set(s["wired"]) >= {"release_manager", "observability"}
    assert all(s["wired"].values())
    assert s["wired_all"] == True
    assert "Understand->Plan" in s["dod_ref"]


def test_release_manager_wired():
    from fabric.registry.deployment_manager import get_deployment_manager

    dm = get_deployment_manager()
    assert dm._get_release_manager() is not None


def test_observability_wired_deploy():
    from fabric.registry.deployment_manager import get_deployment_manager

    dm = get_deployment_manager()
    assert dm._get_observability() is not None


# ---------- Stage 7.2 - CI/CD + K8s (14) ----------


def test_cicd_manager_exists():
    from fabric.registry.cicd_manager import get_cicd_manager

    cm = get_cicd_manager()
    assert cm is not None
    assert get_cicd_manager() is cm


def test_create_pipeline_success():
    from fabric.registry.cicd_manager import get_cicd_manager

    cm = get_cicd_manager()
    r = cm.create_pipeline("unit-pipeline", stages=["build", "test", "verify", "deploy"], actor="tester")
    assert r["success"] == True
    assert r["name"] == "unit-pipeline"
    assert len(r["pipeline"]["stages"]) == 4


def test_create_pipeline_invalid_name():
    from fabric.registry.cicd_manager import get_cicd_manager

    cm = get_cicd_manager()
    r = cm.create_pipeline("", actor="tester")
    assert r["success"] == False
    assert r["canonical_spec"] == CANONICAL_SPEC



def test_generate_k8s_manifest():
    from fabric.registry.cicd_manager import get_cicd_manager

    cm = get_cicd_manager()
    r = cm.generate_k8s_manifest("unit-api", replicas=3, image="mona-apex-core:latest", actor="tester")
    assert r["success"] == True
    assert "manifest" in r
    assert r["manifest"]["kind"] == "Deployment"
    assert r["manifest"]["apiVersion"] == "apps/v1"
    assert r["canonical_spec"] == CANONICAL_SPEC


def test_k8s_replicas_field():
    from fabric.registry.cicd_manager import get_cicd_manager

    cm = get_cicd_manager()
    r = cm.generate_k8s_manifest("unit-api", replicas=3, actor="tester")
    assert r["replicas"] == 3
    assert r["manifest"]["spec"]["replicas"] == 3
    container = r["manifest"]["spec"]["template"]["spec"]["containers"][0]
    assert "livenessProbe" in container
    assert "readinessProbe" in container


def test_run_pipeline_success():
    from fabric.registry.cicd_manager import get_cicd_manager

    cm = get_cicd_manager()
    cm.create_pipeline("run-pipeline", stages=["build", "test", "verify", "deploy"], actor="tester")
    r = cm.run_pipeline("run-pipeline", actor="tester")
    assert r["success"] == True
    assert r["all_checks"] == True
    assert r["result"]["all_ok"] == True


def test_run_pipeline_stages():
    from fabric.registry.cicd_manager import get_cicd_manager

    cm = get_cicd_manager()
    cm.create_pipeline("stages-pipeline", actor="tester")
    r = cm.run_pipeline("stages-pipeline", actor="tester")
    assert r["total"] >= 4
    assert r["passed"] == r["total"]
    assert all(r["result"]["stage_results"].values())


def test_run_pipeline_not_found():
    from fabric.registry.cicd_manager import get_cicd_manager

    cm = get_cicd_manager()
    r = cm.run_pipeline("never-created-pipeline", actor="tester")
    assert r["success"] == False
    assert "not found" in r["reason"]


def test_get_pipelines():
    from fabric.registry.cicd_manager import get_cicd_manager

    cm = get_cicd_manager()
    cm.create_pipeline("listed-pipeline", actor="tester")
    r = cm.get_pipelines()
    assert r["count"] >= 1
    assert r["canonical_spec"] == CANONICAL_SPEC


def test_get_manifests():
    from fabric.registry.cicd_manager import get_cicd_manager

    cm = get_cicd_manager()
    cm.generate_k8s_manifest("listed-api", replicas=3, actor="tester")
    r = cm.get_manifests()
    assert r["count"] >= 1
    assert r["manifests"][-1]["service"] == "listed-api"


def test_deployment_manager_wired():
    from fabric.registry.cicd_manager import get_cicd_manager

    cm = get_cicd_manager()
    assert cm._get_deployment_manager() is not None


def test_canonical_spec_cicd():
    from fabric.registry.cicd_manager import get_cicd_manager

    cm = get_cicd_manager()
    r = cm.create_pipeline("canonical-pipeline", actor="tester")
    assert r["canonical_spec"] == CANONICAL_SPEC
    assert cm.get_stats()["canonical_spec"] == CANONICAL_SPEC
    assert cm.get_pipelines()["canonical_spec"] == CANONICAL_SPEC


def test_zero_cost_cicd():
    from fabric.registry.cicd_manager import get_cicd_manager

    cm = get_cicd_manager()
    r = cm.create_pipeline("zero-cost-pipeline", actor="tester")
    assert r["zero_cost"] == True
    assert cm.get_stats()["zero_cost"] == True


def test_stats_cicd():
    from fabric.registry.cicd_manager import get_cicd_manager

    cm = get_cicd_manager()
    s = cm.get_stats()
    assert "total_pipelines" in s
    assert "total_manifests" in s
    assert s["total_pipelines"] >= 1
    assert s["total_manifests"] >= 1
    assert all(s["wired"].values())
    assert "Understand->Plan" in s["dod_ref"]
