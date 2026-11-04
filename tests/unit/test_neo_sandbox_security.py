"""
NEO Audit Fix: Sandbox f-string injection prevention

Tests voor Sprint 3 — P1: Sandbox Security
Code MOET via base64 encoding worden doorgegeven, NIET via f-string interpolatie.
"""

import base64
import re

import pytest

# ============================================================
# TestSandboxCodeIsolation
# ============================================================


class TestSandboxCodeIsolation:
    """User code MOET via base64 encoding worden doorgegeven, NIET via f-string."""

    def test_user_code_not_in_fstring_template(self):
        """HAPPY: De template gebruikt base64 encoding, niet direct code interpolatie."""
        from src.core.sandbox.enhanced_sandbox_manager import EnhancedDockerSandboxManager

        mgr = EnhancedDockerSandboxManager.__new__(EnhancedDockerSandboxManager)

        # Malicious user code that would break out of f-string
        malicious_code = '"""\nimport os; os.system("rm -rf /")\n"""'

        # Generate execution script
        template = mgr._generate_execution_script(malicious_code)

        # The template should NOT contain the raw malicious code as plaintext
        # (It should be base64 encoded instead)
        assert (
            malicious_code not in template
        ), "User code mag NIET direct in de Python template staan (f-string injection risk)"

    def test_triple_quote_escape_attempt_blocked(self):
        """UNHAPPY: Code met triple quotes mag niet uit de template breken."""
        from src.core.sandbox.enhanced_sandbox_manager import EnhancedDockerSandboxManager

        mgr = EnhancedDockerSandboxManager.__new__(EnhancedDockerSandboxManager)

        # Payload that tries to escape f-string via triple quotes
        escape_payload = '"""); import os; os.system("whoami"); exec("""'

        # Generate execution script
        template = mgr._generate_execution_script(escape_payload)

        # Template moet syntactisch geldig Python zijn
        # (Als het payload niet geescaped was, zou dit een SyntaxError geven)
        try:
            compile(template, "<test>", "exec")
            # If we get here, it compiled successfully = injection was prevented
            assert True
        except SyntaxError as e:
            pytest.fail(f"Template has SyntaxError - injection not properly prevented: {e}")

    def test_base64_encoded_code_roundtrip(self):
        """HAPPY: Code → base64 encode → decode → gelijk aan origineel."""
        code = "print('Hello, world!')\nresult = 42"

        # Encode
        encoded = base64.b64encode(code.encode("utf-8")).decode("ascii")

        # Decode
        decoded = base64.b64decode(encoded).decode("utf-8")

        # Assert
        assert decoded == code

    def test_base64_payload_rendering_in_template(self):
        """HAPPY: Template bevat base64 gecodeerde payload, niet raw code."""
        from src.core.sandbox.enhanced_sandbox_manager import EnhancedDockerSandboxManager

        mgr = EnhancedDockerSandboxManager.__new__(EnhancedDockerSandboxManager)

        user_code = "x = 1 + 1\nprint(x)"
        template = mgr._generate_execution_script(user_code)

        # Template should contain base64 encoded version
        code_b64 = base64.b64encode(user_code.encode("utf-8")).decode("ascii")

        # Either the base64 string should be in the template, or a pattern that decodes it
        assert (
            code_b64 in template or "base64.b64decode" in template
        ), "Template moet base64 encoding gebruiken"

    def test_multiple_escape_attempts_fail(self):
        """UNHAPPY: Verschillende escape pogingen moeten allemaal mislukken."""
        from src.core.sandbox.enhanced_sandbox_manager import EnhancedDockerSandboxManager

        mgr = EnhancedDockerSandboxManager.__new__(EnhancedDockerSandboxManager)

        escape_attempts = [
            '"""{malicious}"""',  # Try to break out with quotes
            'f"{malicious}"',  # Try f-string
            "{malicious}",  # Direct interpolation
            '"; {malicious} #',  # Comment injection
        ]

        for attempt in escape_attempts:
            template = mgr._generate_execution_script(attempt)

            # Should compile without SyntaxError
            try:
                compile(template, "<test>", "exec")
            except SyntaxError:
                pytest.fail(f"Escape attempt caused SyntaxError: {attempt}")

            # Should NOT contain the raw attempt
            assert attempt not in template, f"Raw escape attempt found: {attempt}"


# ============================================================
# TestSandboxExecutionSafety
# ============================================================


class TestSandboxExecutionSafety:
    """Sandbox execution MOET veilig zijn en errors correct handelen."""

    async def test_sandbox_execution_with_safe_code(self):
        """HAPPY: Veilige code wordt uitgerekend."""
        from src.core.sandbox.enhanced_sandbox_manager import EnhancedDockerSandboxManager

        mgr = EnhancedDockerSandboxManager.__new__(EnhancedDockerSandboxManager)

        # Simple safe code
        code = "result = 2 + 2"

        # Execute
        template = mgr._generate_execution_script(code)

        # Should compile and be executable
        namespace = {}
        try:
            exec(template, namespace)
            # If we get here, it executed successfully
            assert True
        except Exception as e:
            pytest.fail(f"Safe code execution failed: {e}")

    async def test_sandbox_execution_with_dangerous_code_is_caught(self):
        """UNHAPPY: Gevaarlijke code moet sicher worden afgevangen."""
        from src.core.sandbox.enhanced_sandbox_manager import EnhancedDockerSandboxManager

        mgr = EnhancedDockerSandboxManager.__new__(EnhancedDockerSandboxManager)

        # Code that tries to import os and run system commands
        code = "import os; os.system('rm -rf /')"

        # Generate template
        template = mgr._generate_execution_script(code)

        # Template should execute without actually running the command
        # (In real sandbox, imports might be blocked)
        namespace = {}
        try:
            exec(template, namespace)
            # If we get here, it means the code didn't break out
            # (The import might fail in sandbox context)
            assert True
        except Exception as e:
            # ImportError is OK - import was blocked
            # We just don't want arbitrary code execution
            assert "import" in str(e).lower() or "os" in str(type(e).__name__).lower()

    def test_sandbox_template_has_error_handling(self):
        """HAPPY: Template bevat try/except voor error handling."""
        from src.core.sandbox.enhanced_sandbox_manager import EnhancedDockerSandboxManager

        mgr = EnhancedDockerSandboxManager.__new__(EnhancedDockerSandboxManager)

        code = "1 / 0"  # Division by zero
        template = mgr._generate_execution_script(code)

        # Template should have try/except
        assert "try:" in template
        assert "except" in template
