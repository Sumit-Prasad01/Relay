import pytest
from Relay.security.command_policy import CommandPolicy, CommandRisk


def test_split_command_with_quotes():
    cmd = 'grep "foo|bar" file.txt && echo "done; next"'
    parts = CommandPolicy.split_command(cmd)
    assert len(parts) == 2
    assert parts[0] == 'grep "foo|bar" file.txt'
    assert parts[1] == 'echo "done; next"'


def test_classify_commands():
    # Read-only
    assert CommandPolicy.classify("ls -la")[0] == CommandRisk.READ_ONLY
    assert CommandPolicy.classify("git status")[0] == CommandRisk.READ_ONLY
    assert CommandPolicy.classify("cat README.md")[0] == CommandRisk.READ_ONLY

    # Mutation
    assert CommandPolicy.classify("pytest tests/")[0] == CommandRisk.MUTATION
    assert CommandPolicy.classify("ruff format .")[0] == CommandRisk.MUTATION

    # Network
    assert CommandPolicy.classify("curl https://example.com")[0] == CommandRisk.NETWORK
    assert CommandPolicy.classify("git push origin main")[0] == CommandRisk.NETWORK

    # Destructive
    assert CommandPolicy.classify("rm -rf node_modules")[0] == CommandRisk.DESTRUCTIVE
    assert CommandPolicy.classify("git reset --hard")[0] == CommandRisk.DESTRUCTIVE

    # Privileged
    assert CommandPolicy.classify("sudo apt-get update")[0] == CommandRisk.PRIVILEGED
    assert CommandPolicy.classify("chmod 777 script.sh")[0] == CommandRisk.PRIVILEGED


def test_compound_command_highest_risk_wins():
    compound = "git status && rm -rf build"
    risk, parts = CommandPolicy.classify(compound)
    assert len(parts) == 2
    assert risk == CommandRisk.DESTRUCTIVE
