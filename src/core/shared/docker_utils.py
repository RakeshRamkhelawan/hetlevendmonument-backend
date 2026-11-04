import logging

try:
    import docker
    from docker.errors import DockerException
except ImportError:
    docker = None
    DockerException = Exception

logger = logging.getLogger(__name__)


def check_docker_availability() -> bool:
    """
    Checks if the Docker daemon is running and accessible.
    Returns True if Docker is available, False otherwise.
    """
    if docker is None:
        logger.warning("Docker library not installed")
        return False
    try:
        client = docker.from_env()
        client.ping()
        logger.info("Docker daemon is running and accessible.")
        return True
    except DockerException as e:
        logger.error(f"Docker daemon is not accessible: {e}")
        return False
    except Exception as e:
        logger.error(f"An unexpected error occurred while checking Docker: {e}")
        return False


if __name__ == "__main__":
    if check_docker_availability():
        print("Docker is available.")
    else:
        print("Docker is NOT available.")
