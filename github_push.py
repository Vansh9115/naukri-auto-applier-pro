import os
import sys
import json
from dulwich.repo import Repo
from dulwich import porcelain

def load_config():
    cfg_path = os.path.join(os.path.dirname(__file__), "config.json")
    if os.path.exists(cfg_path):
        with open(cfg_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def push_to_github():
    repo_path = os.path.abspath(os.path.dirname(__file__))
    if not os.path.exists(os.path.join(repo_path, '.git')):
        repo = Repo.init(repo_path)
    else:
        repo = Repo(repo_path)
    
    remote_url = "https://github.com/Vansh9115/naukri-auto-applier-pro.git"
    cfg = repo.get_config()
    cfg.set(("remote", "origin"), "url", remote_url.encode('utf-8'))
    cfg.write_to_path()

    print("Staging files...")
    porcelain.add(repo)
    try:
        commit_id = porcelain.commit(repo, message=b"Sync Web App and software updates to GitHub")
        print(f"Committed SHA: {commit_id.decode()[:7]}")
    except Exception as e:
        print(f"Commit note: {e}")

    repo.refs[b'refs/heads/main'] = repo.head()

    cfg_data = load_config()
    pat = cfg_data.get("github_token", os.environ.get("GITHUB_TOKEN", "")).strip()

    if not pat:
        pat = input("Enter your GitHub Personal Access Token (PAT): ").strip()

    if pat:
        auth_url = f"https://Vansh9115:{pat}@github.com/Vansh9115/naukri-auto-applier-pro.git"
        try:
            print("Pushing repository to GitHub...")
            porcelain.push(repo, auth_url, refspecs=b"refs/heads/main:refs/heads/main", force=True)
            print("SUCCESS! Pushed repository to https://github.com/Vansh9115/naukri-auto-applier-pro")
        except Exception as ex:
            print(f"Push error: {ex}")

if __name__ == "__main__":
    push_to_github()
