"""Bind fresh owned runtime resources to existing independent test cases."""

from test_agents.test_runtime.models import RunnerCase


def prepare_runner(test):
    case = RunnerCase.create()
    test.addCleanup(case.close)
    test.case = case
    test.root = case.root
    test.source = case.source
    test.skill_source = case.skill_source
    test.revision = case.revision
    test.runner = case.runner
