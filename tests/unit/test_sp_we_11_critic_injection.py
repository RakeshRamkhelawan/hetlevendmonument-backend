"""SP-WE-11 legacy test file -- superseded by test_sp_we_11_critic_orchestrator_wiring.py.

The original tests verified constructor injection (critic= parameter) and direct
critique_task() calls with cast(Any, ...). That approach was replaced in SP-WE-11
with CriticMixin.post_process_task() to eliminate the Any-antipattern and the
constructor-injection pattern inconsistent with AgentHealthMonitorAgent/AgentRouterAgent.

See: tests/unit/test_sp_we_11_critic_orchestrator_wiring.py for the full 8-test suite.
"""
