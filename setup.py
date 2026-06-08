from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="etclovg-harness",
    version="1.0.0",
    author="ETCLOVG Research",
    description="Production-Grade Seven-Layer Agent Harness (E·T·C·L·O·V·G)",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/dolannb/etclovg-harness",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
    ],
    python_requires=">=3.10",
    install_requires=[
        "openai>=1.12.0",
        "pydantic>=2.0.0",
        "typing-extensions>=4.8.0",
    ],
    entry_points={
        "console_scripts": [
            "etclovg=agent:main",
        ],
    },
)
