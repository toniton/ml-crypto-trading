from setuptools import setup, find_packages


if __name__ == "__main__":
    setup(
        name='rio-api',
        version='1.0.0',
        packages=find_packages(),
        install_requires=[
            # List your dependencies here
            "pydantic~=2.5.2",
            "websocket-client~=1.7.0",
            "uuid~=1.30",
        ],
    )
