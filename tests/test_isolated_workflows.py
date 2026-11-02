import ast
from pathlib import Path

root=Path("custom_components/smoobu_mittelhof")
tree=ast.parse((root/"workflow.py").read_text(encoding="utf-8"))
cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=="WorkflowManager")
methods={n.name:n for n in cls.body if isinstance(n,ast.AsyncFunctionDef)}
for method in ("async_process_laundry_only","async_process_nuki_only"):
    assert method in methods,method
    source=ast.get_source_segment((root/"workflow.py").read_text(encoding="utf-8"),methods[method])
    assert "_lock" in source and "await self._persist()" in source
    called=[n.attr for n in ast.walk(methods[method]) if isinstance(n,ast.Attribute)]
    expected="_process_laundry" if "laundry" in method else "_process_nuki"
    forbidden="_process_nuki" if "laundry" in method else "_process_laundry"
    assert expected in called,(method,called)
    assert forbidden not in called,(method,called)

service=(root/"services.py").read_text(encoding="utf-8")
button=(root/"button.py").read_text(encoding="utf-8")
assert "SERVICE_PROCESS_NUKI_ONLY" in service and "SERVICE_PROCESS_LAUNDRY_ONLY" in service
assert "async_process_nuki_only(force_notify=True)" in button
assert "async_process_laundry_only(force_notify=True)" in button
assert "ProcessWorkflowsButton(runtime, entry.entry_id)" not in button
print("PASS: standalone NUKI and laundry actions never cross-call each other")
