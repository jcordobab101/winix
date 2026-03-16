from pathlib import Path

from setuptools import find_packages, setup


BASE_DIR = Path(__file__).resolve().parent
README = BASE_DIR / "README.md"

long_description = README.read_text(encoding="utf-8") if README.exists() else ""


setup(
    name="winix",
    version="0.4.0",
    author="Joshua Cordoba",
    author_email="jcordobab101@icloud.com",
    description="Modern Winix Integration",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/jcordobab101/winix",
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        "boto3>=1.34.0",
        "botocore>=1.34.0",
        "requests>=2.31.0",
        "python-dotenv>=1.0.0",
    ],
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.10",
    entry_points={
        "console_scripts": [
            "winix=winix.cmd:main",
            "winixctl=winix.cmd:main",
        ],
    },
)