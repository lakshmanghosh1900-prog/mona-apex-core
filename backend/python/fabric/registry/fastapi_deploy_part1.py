from fastapi import APIRouter, Query
from typing import Optional
import traceback

router = APIRouter()

CANONICAL_SPEC = "MONA - Powered by Apex Core"


@router.get("/phase7/stage7.1/verify")
def verify_stage_7_1():
    checks = {}
    try:
        from fabric.registry.deployment_manager import get_deployment_manager

        dm = get_deployment_manager()
        dm.deployments.clear()
        dm.health_checks.clear()

        checks["1_deployment_exists"] = dm is not None

        r_deploy = dm.deploy("2.0.0-test", env="test", actor="verifier")
        checks["2_deploy"] = r_deploy.get("success") == True

        r_health = dm.health_probe("api")
        checks["3_health_probe"] = "healthy" in r_health and "checks" in r_health
        checks["4_health_all_ok"] = r_health.get("all_checks") == True or r_health.get("healthy") == True

        r_get = dm.get_deployments()
        checks["5_get_deployments"] = r_get.get("count", 0) >= 1

        r_hist = dm.get_health_history()
        checks["6_health_history"] = r_hist.get("count", 0) >= 1

        checks["7_release_wired"] = dm._get_release_manager() is not None
        checks["8_observability_wired"] = dm._get_observability() is not None

        checks["9_env_field"] = r_deploy.get("deployment", {}).get("env") == "test"
        checks["10_canonical_spec"] = r_deploy.get("canonical_spec") == CANONICAL_SPEC
        checks["11_zero_cost_isolated"] = r_deploy.get("zero_cost") == True and r_deploy.get("isolated") == True

        stats = dm.get_stats()
        checks["12_stats"] = "total_deployments" in stats and stats.get("canonical_spec") == CANONICAL_SPEC
        checks["13_wired"] = "wired" in stats and all(stats.get("wired", {}).values())
        checks["14_health_stats"] = "total_health_checks" in stats

        all_ok = all(checks.values())
        return {
            "stage": "Phase 7 Stage 7.1 — Deployment Manager",
            "status": "✅ COMPLETE" if all_ok else "❌ INCOMPLETE",
            "all_checks": all_ok,
            "checks": checks,
            "passed": sum(1 for v in checks.values() if v),
            "failed": sum(1 for v in checks.values() if not v),
            "total": len(checks),
            "stats": stats,
            "canonical_spec": CANONICAL_SPEC,
            "zero_cost": True,
        }
    except Exception as ex:
        return {
            "stage": "Phase 7 Stage 7.1",
            "status": f"ERROR: {ex}",
            "all_checks": False,
            "error": str(ex),
            "traceback": traceback.format_exc(),
            "checks": checks,
            "canonical_spec": CANONICAL_SPEC,
        }


@router.get("/phase7/stage7.2/verify")
def verify_stage_7_2():
    checks = {}
    try:
        from fabric.registry.cicd_manager import get_cicd_manager

        cm = get_cicd_manager()
        cm.pipelines.clear()
        cm.k8s_manifests.clear()

        checks["1_cicd_exists"] = cm is not None

        r_pipe = cm.create_pipeline("test-pipeline-72", stages=["build", "test", "verify", "deploy"], actor="verifier")
        checks["2_create_pipeline"] = r_pipe.get("success") == True

        r_manifest = cm.generate_k8s_manifest("mona-api", replicas=3, image="mona-apex-core:latest", actor="verifier")
        checks["3_generate_k8s"] = r_manifest.get("success") == True and "manifest" in r_manifest

        r_run = cm.run_pipeline("test-pipeline-72", actor="verifier")
        checks["4_run_pipeline"] = r_run.get("success") == True
        checks["5_pipeline_stages"] = r_run.get("total", 0) >= 4

        r_get = cm.get_pipelines()
        checks["6_get_pipelines"] = r_get.get("count", 0) >= 1

        r_get_m = cm.get_manifests()
        checks["7_get_manifests"] = r_get_m.get("count", 0) >= 1

        checks["8_deployment_wired"] = cm._get_deployment_manager() is not None
        checks["9_replicas"] = r_manifest.get("replicas") == 3
        checks["10_canonical_spec"] = r_pipe.get("canonical_spec") == CANONICAL_SPEC
        checks["11_zero_cost"] = r_pipe.get("zero_cost") == True

        stats = cm.get_stats()
        checks["12_stats"] = "total_pipelines" in stats and stats.get("canonical_spec") == CANONICAL_SPEC
        checks["13_wired"] = "wired" in stats and all(stats.get("wired", {}).values())
        checks["14_manifests_stats"] = "total_manifests" in stats

        all_ok = all(checks.values())
        return {
            "stage": "Phase 7 Stage 7.2 — CI/CD + K8s",
            "status": "✅ COMPLETE" if all_ok else "❌ INCOMPLETE",
            "all_checks": all_ok,
            "checks": checks,
            "passed": sum(1 for v in checks.values() if v),
            "failed": sum(1 for v in checks.values() if not v),
            "total": len(checks),
            "stats": stats,
            "canonical_spec": CANONICAL_SPEC,
            "zero_cost": True,
        }
    except Exception as ex:
        return {
            "stage": "Phase 7 Stage 7.2",
            "status": f"ERROR: {ex}",
            "all_checks": False,
            "error": str(ex),
            "traceback": traceback.format_exc(),
            "checks": checks,
            "canonical_spec": CANONICAL_SPEC,
        }


@router.get("/deploy/deployments")
def deploy_list(limit: int = Query(20, ge=1, le=200)):
    try:
        from fabric.registry.deployment_manager import get_deployment_manager

        return get_deployment_manager().get_deployments(limit=limit)
    except Exception as e:
        return {"error": str(e), "canonical_spec": CANONICAL_SPEC}


@router.get("/deploy/health")
def deploy_health(component: str = Query("api")):
    try:
        from fabric.registry.deployment_manager import get_deployment_manager

        return get_deployment_manager().health_probe(component)
    except Exception as e:
        return {"error": str(e), "canonical_spec": CANONICAL_SPEC}


@router.get("/deploy/stats")
def deploy_stats():
    try:
        from fabric.registry.deployment_manager import get_deployment_manager

        return get_deployment_manager().get_stats()
    except Exception as e:
        return {"error": str(e), "canonical_spec": CANONICAL_SPEC}


@router.get("/cicd/pipelines")
def cicd_pipelines(limit: int = Query(20, ge=1, le=200)):
    try:
        from fabric.registry.cicd_manager import get_cicd_manager

        return get_cicd_manager().get_pipelines(limit=limit)
    except Exception as e:
        return {"error": str(e), "canonical_spec": CANONICAL_SPEC}


@router.get("/cicd/manifests")
def cicd_manifests(limit: int = Query(20, ge=1, le=200)):
    try:
        from fabric.registry.cicd_manager import get_cicd_manager

        return get_cicd_manager().get_manifests(limit=limit)
    except Exception as e:
        return {"error": str(e), "canonical_spec": CANONICAL_SPEC}


@router.get("/cicd/stats")
def cicd_stats():
    try:
        from fabric.registry.cicd_manager import get_cicd_manager

        return get_cicd_manager().get_stats()
    except Exception as e:
        return {"error": str(e), "canonical_spec": CANONICAL_SPEC}
