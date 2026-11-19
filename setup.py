from setuptools import setup, find_packages

setup(
    name="relay",
    version="0.1.0",
    description="A lightweight coding agent",
    packages=find_packages(),
    install_requires=[
        "openai",
        "prompt-toolkit",
        "pyyaml",
        "rich",
    ],
    entry_points={
        "console_scripts": [
            "relay=Relay.agent:main",
        ],
    },
    python_requires=">=3.10",
)
