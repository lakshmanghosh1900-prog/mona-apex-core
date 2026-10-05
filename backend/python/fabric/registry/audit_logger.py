import time, json, pathlib, hashlib, re
from typing import Dict, List, Any, Optional

AUDIT_ROOT = pathlib.Path("/tmp/mona_sandbox/audit")
AUDIT_ROOT.mkdir(parents=True, exist_ok=True)

SECRET_PATTERNS = [r'GROQ_API_KEY\s*[=:]\s*[^\s"]+', r'GEMINI_API_KEY\s*[=:]\s*[^\s"]+', r'TELEGRAM_BOT_TOKEN\s*[=:]\s*[^\s"]+', r'"GROQ_API_KEY"\s*:\s*"[^"]*"', r'"GEMINI_API_KEY"\s*:\s*"[^"]*"', r'"TELEGRAM_BOT_TOKEN"\s*:\s*"[^"]*"', r"\b\d{8,10}:[A-Za-z0-9_\-]{20,}", r"GROQ_API_KEY", r"GEMINI_API_KEY", r"TELEGRAM_BOT_TOKEN", r"sk-[a-zA-Z0-9]{20,}", r"gsk_[a-zA-Z0-9]{8,}"]

def _scrub(text: str) -> str:
    out = text
    for pat in SECRET_PATTERNS:
        out = re.sub(pat, "[REDACTED]", out, flags=re.IGNORECASE)
    return out

class EvidenceChain:
    def __init__(self):
        self.chain: List[Dict] = []
    def add(self, data: Dict) -> Dict:
        prev_hash = self.chain[-1]["hash"] if self.chain else "0"*64
        payload = json.dumps(data, sort_keys=True, default=str)
        curr_hash = hashlib.sha256((prev_hash + payload).encode()).hexdigest()
        block = {
            "index": len(self.chain),
            "timestamp": time.time(),
            "data": data,
            "prev_hash": prev_hash,
            "hash": curr_hash,
            "canonical_spec": "MONA - Powered by Apex Core",
            "dod_ref": "Understand->Plan->Select Model->Select Tool->Check Permission->Approval->Execute in Sandbox->Observe->Verify->Self-Heal->Evidence->Memory->Report->Resume Later"
        }
        self.chain.append(block)
        return block
    def verify_chain(self) -> Dict:
        if len(self.chain) == 0:
            return {"valid": True, "length": 0, "tampered": False}
        for i in range(1, len(self.chain)):
            prev = self.chain[i-1]
            curr = self.chain[i]
            if curr["prev_hash"] != prev["hash"]:
                return {"valid": False, "tampered_at": i, "reason": "prev_hash mismatch", "length": len(self.chain)}
            payload = json.dumps(curr["data"], sort_keys=True, default=str)
            recomputed = hashlib.sha256((prev["hash"] + payload).encode()).hexdigest()
            if recomputed != curr["hash"]:
                return {"valid": False, "tampered_at": i, "reason": "hash mismatch", "length": len(self.chain)}
        return {"valid": True, "length": len(self.chain), "tampered": False}
    def get_chain(self, limit: int = 50) -> List[Dict]:
        return self.chain[-limit:]

class AuditLogger:
    def __init__(self):
        self.logs: List[Dict] = []
        self.chain = EvidenceChain()

    def log(self, tool_name: str, actor: str, role: str, inputs: Dict, result: Dict, approved: bool = True, policy_decision: str = "ALLOW") -> Dict:
        # Scrub secrets from inputs for storage
        safe_inputs_str = _scrub(json.dumps(inputs, default=str))
        try:
            safe_inputs = json.loads(safe_inputs_str)
        except:
            safe_inputs = {"scrubbed": safe_inputs_str}

        entry = {
            "timestamp": time.time(),
            "tool": tool_name,
            "actor": actor,
            "role": role,
            "inputs": safe_inputs,
            "result_success": result.get("success", result.get("ok", False)),
            "result": result,
            "approved": approved,
            "policy_decision": policy_decision,
            "evidence_id": f"ev_{int(time.time()*1000)}_{len(self.logs)}",
            "canonical_spec": "MONA - Powered by Apex Core",
            "dod_ref": "Understand->Plan->Select Model->Select Tool->Check Permission->Approval->Execute in Sandbox->Observe->Verify->Self-Heal->Evidence->Memory->Report->Resume Later",
            "stack": "zero-cost"
        }
        self.logs.append(entry)
        # Write to file
        try:
            log_file = AUDIT_ROOT / f"{entry['evidence_id']}.json"
            log_file.write_text(json.dumps(entry, indent=2, default=str))
            entry["file_written"] = True
            entry["file_path"] = str(log_file)
        except Exception as e:
            entry["file_written"] = False
            entry["file_error"] = str(e)

        # Add to evidence chain
        chain_block = self.chain.add({"evidence_id": entry["evidence_id"], "tool": tool_name, "actor": actor, "policy": policy_decision})
        entry["chain_index"] = chain_block["index"]
        entry["chain_hash"] = chain_block["hash"]
        return entry

    def get_trail(self, tool_name: Optional[str] = None, actor: Optional[str] = None, limit: int = 50) -> Dict:
        filtered = self.logs
        if tool_name:
            filtered = [l for l in filtered if l["tool"] == tool_name]
        if actor:
            filtered = [l for l in filtered if l["actor"] == actor]
        return {
            "count": len(filtered),
            "filtered_count": len(filtered[-limit:]),
            "trail": filtered[-limit:],
            "audit_root": str(AUDIT_ROOT),
            "chain_length": len(self.chain.chain),
            "chain_valid": self.chain.verify_chain()["valid"]
        }

    def get_stats(self) -> Dict:
        tools = {}
        roles = {}
        for log in self.logs:
            tools[log["tool"]] = tools.get(log["tool"], 0) + 1
            roles[log["role"]] = roles.get(log["role"], 0) + 1
        return {
            "total_logs": len(self.logs),
            "tools": tools,
            "roles": roles,
            "audit_root": str(AUDIT_ROOT),
            "chain_length": len(self.chain.chain),
            "chain_valid": self.chain.verify_chain()["valid"],
            "files_on_disk": len(list(AUDIT_ROOT.glob("ev_*.json")))
        }

# Singleton
_audit_logger_instance = None

def get_audit_logger() -> AuditLogger:
    global _audit_logger_instance
    if _audit_logger_instance is None:
        _audit_logger_instance = AuditLogger()
    return _audit_logger_instance

def get_evidence_chain() -> EvidenceChain:
    return get_audit_logger().chain
