from backend.tools import code_runner
from backend.run_artifacts import get_verification_runs, reset_verification_runs


def test_execute_python_code_cleans_up_temp_file(active_project):
    reset_verification_runs()
    before = {path.name for path in active_project.iterdir()}

    result = code_runner.execute_code("print('ok')\n", "python")

    after = {path.name for path in active_project.iterdir()}
    assert result["success"] is True
    assert result["stdout"].strip() == "ok"
    assert before == after
    assert get_verification_runs()[-1]["kind"] == "inline"
    assert get_verification_runs()[-1]["classification"] == "python_inline"


def test_execute_javascript_file(active_project):
    reset_verification_runs()
    script = active_project / "hello.js"
    script.write_text("console.log('hello from js');\n", encoding="utf-8")

    result = code_runner.execute_file("hello.js")

    assert result["success"] is True
    assert "hello from js" in result["stdout"]
    assert result["runtime"] == "javascript"
    assert get_verification_runs()[-1]["target"] == "hello.js"
    assert get_verification_runs()[-1]["classification"] == "javascript_file"


def test_execute_typescript_file(active_project):
    reset_verification_runs()
    script = active_project / "hello.ts"
    script.write_text("const value: number = 7;\nconsole.log(value);\n", encoding="utf-8")

    result = code_runner.execute_file("hello.ts")

    assert result["success"] is True
    assert result["stdout"].strip() == "7"
    assert result["runtime"] == "typescript"


def test_execute_project_command_rejects_unsafe_python_eval(active_project):
    reset_verification_runs()
    result = code_runner.run_project_command.invoke({"command": "python -c print('bad')"})

    assert result.startswith("ERROR ")
    assert "python -m pytest" in result


def test_execute_project_command_runs_node_project_file(active_project):
    reset_verification_runs()
    script = active_project / "verify-check.js"
    script.write_text("console.log('verify ok');\n", encoding="utf-8")

    result = code_runner.execute_project_command("node verify-check.js")

    assert result["success"] is True
    assert "verify ok" in result["stdout"]
    assert get_verification_runs()[-1]["kind"] == "command"
    assert "node" in get_verification_runs()[-1]["target"]
    assert get_verification_runs()[-1]["classification"] == "node_verification_script"


def test_execute_project_command_rejects_non_verification_node_script(active_project):
    script = active_project / "server.js"
    script.write_text("console.log('server');\n", encoding="utf-8")

    result = code_runner.run_project_command.invoke({"command": "node server.js"})

    assert result.startswith("ERROR ")
    assert "verification-oriented" in result
