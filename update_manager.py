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

        # 4. Update external tools (Go & Cloned repos)
        if not self._update_tools():
            logger.error("Failed to update external tools.")
            return False

        logger.info("BBH-AI and all tools updated successfully.")
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
    def _update_tools(self):
        """Re-runs installation for core security tools to ensure latest versions."""
        logger.info("Updating external security tools...")
        
        # Check for Go
        has_go = subprocess.run(["go", "version"], capture_output=True, check=False).returncode == 0
        if not has_go:
            logger.warning("Go is not installed. Skipping Go-based tool updates.")
        else:
            # Go tools
            go_tools = [
                "github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest",
                "github.com/projectdiscovery/httpx/cmd/httpx@latest",
                "github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest",
                "github.com/projectdiscovery/katana/cmd/katana@latest",
                "github.com/projectdiscovery/dnsx/cmd/dnsx@latest",
                "github.com/projectdiscovery/interactsh/cmd/interactsh-client@latest",
                "github.com/tomnomnom/assetfinder@latest",
                "github.com/lc/gau/v2/cmd/gau@latest",
                "github.com/hahwul/dalfox/v2@latest",
                "github.com/jaeles-project/gospider@latest",
                "github.com/ffuf/ffuf@latest"
            ]
            
            for tool in go_tools:
                logger.info(f"Updating {tool}...")
                subprocess.run(["go", "install", "-v", tool], check=False)

        # Git tools in /opt (pull updates)
        opt_tools = ["Sublist3r", "waymore", "CMSeeK", "dorks_hunter", "regulator", "AnalyticsRelationships"]
        # Check if /opt exists or we have permission
        if not os.path.exists("/opt"):
            logger.warning("/opt directory does not exist. Skipping auxiliary tool updates.")
            return True

        for tool in opt_tools:
            tool_path = os.path.join("/opt", tool)
            if os.path.exists(tool_path):
                logger.info(f"Updating {tool} in /opt...")
                subprocess.run(["git", "pull"], cwd=tool_path, check=False)
                # Re-run install for python tools
                if os.path.exists(os.path.join(tool_path, "setup.py")):
                    subprocess.run([sys.executable, "-m", "pip", "install", "."], cwd=tool_path, check=False)
                elif os.path.exists(os.path.join(tool_path, "requirements.txt")):
                    subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], cwd=tool_path, check=False)

        return True
