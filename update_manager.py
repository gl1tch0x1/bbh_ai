import subprocess
import sys
import os
import logging

logger = logging.getLogger(__name__)

class UpdateManager:
    """
    Handles self-updating logic for bbh-ai via git and pip.
    """
    def __init__(self, root_dir):
        self.root_dir = root_dir

    def update(self):
        """
        Performs the update process: git pull and pip install.
        """
        logger.info("Starting BBH-AI update process...")
        
        # 1. Check if git is available and is a git repo
        if not self._is_git_repo():
            logger.error("Not a git repository. Auto-update requires bbh-ai to be cloned via git.")
            return False

        # 2. git pull
        if not self._git_pull():
            logger.error("Failed to pull latest changes from git.")
            return False

        # 3. pip install -r requirements.txt
        if not self._update_dependencies():
            logger.error("Failed to update dependencies.")
            return False

        logger.info("BBH-AI updated successfully. Please restart the application if needed.")
        return True

    def _is_git_repo(self):
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--is-inside-work-tree"],
                cwd=self.root_dir,
                capture_output=True,
                text=True,
                check=False
            )
            return result.returncode == 0
        except FileNotFoundError:
            return False

    def _git_pull(self):
        logger.info("Pulling latest code from origin...")
        try:
            result = subprocess.run(
                ["git", "pull", "origin", "main"],
                cwd=self.root_dir,
                capture_output=True,
                text=True,
                check=False
            )
            if result.returncode != 0:
                logger.error(f"git pull error: {result.stderr.strip()}")
                return False
            logger.info(result.stdout.strip())
            return True
        except Exception as e:
            logger.error(f"Exception during git pull: {e}")
            return False

    def _update_dependencies(self):
        req_file = os.path.join(self.root_dir, "requirements.txt")
        if not os.path.exists(req_file):
            logger.warning("No requirements.txt found. Skipping dependency update.")
            return True
        
        logger.info("Updating dependencies via pip...")
        try:
            # sys.executable is the current python interpreter
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
                cwd=self.root_dir,
                capture_output=True,
                text=True,
                check=False
            )
            if result.returncode != 0:
                logger.error(f"pip install error: {result.stderr.strip()}")
                return False
            logger.info("Dependencies updated successfully.")
            return True
        except Exception as e:
            logger.error(f"Exception during dependency update: {e}")
            return False
