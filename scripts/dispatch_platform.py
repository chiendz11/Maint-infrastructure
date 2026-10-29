from __future__ import annotations

import json
import os
import subprocess
import time
from urllib.request import Request,urlopen
import jwt

from build_platform_contract import build
from terraform_run import initialize,ROOT


def main() -> None:
    initialize("platform")
    raw=subprocess.check_output(["terraform","-chdir=terraform/platform","output","-json"],cwd=ROOT,text=True)
    contract=build(json.loads(raw))
    now=int(time.time())
    signed=jwt.encode({"iat":now-30,"exp":now+540,"iss":os.environ["GITHUB_APP_ID"]},os.environ["GITHUB_APP_PRIVATE_KEY"],algorithm="RS256")
    repo=os.environ["GITHUB_TARGET_REPOSITORY"]
    request=Request(f'https://api.github.com/app/installations/{int(os.environ["GITHUB_APP_INSTALLATION_ID"])}/access_tokens',data=json.dumps({"repositories":[repo.split("/",1)[1]],"permissions":{"actions":"write"}}).encode(),headers={"Authorization":"Bearer "+signed,"Accept":"application/vnd.github+json"},method="POST")
    with urlopen(request,timeout=30) as response:token=json.load(response)["token"]
    request=Request(f"https://api.github.com/repos/{repo}/actions/workflows/platform-reconcile.yml/dispatches",data=json.dumps({"ref":"main","inputs":{"intent":json.dumps(contract,separators=(",",":"))}}).encode(),headers={"Authorization":"Bearer "+token,"Accept":"application/vnd.github+json","X-GitHub-Api-Version":"2022-11-28"},method="POST")
    with urlopen(request,timeout=30) as response:
        if response.status!=204:raise ValueError("Platform dispatch was not acknowledged")
    print("Platform handoff dispatched; this does not mean a PR was merged or Argo synchronized.")

if __name__=="__main__":main()
