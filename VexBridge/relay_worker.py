from __future__ import annotations
import asyncio, base64, hashlib, json, os, secrets, subprocess, sys, time, zlib
from pathlib import Path
from typing import Any
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

REPO="hiitsmestar/vex-native"
OWNER="hiitsmestar"
ISSUE=84
MCP_URL="http://127.0.0.1:8795/mcp"
POLL_SECONDS=10
APP=Path(os.environ.get("APPDATA", str(Path.home())))/"VexBridgeDC"
KEY_FILE=APP/"relay-private.key"
STATE_FILE=APP/"relay-state.json"
STATUS_FILE=APP/"relay-status.json"
LOG_FILE=APP/"relay.log"
APP.mkdir(parents=True, exist_ok=True)

def b64e(data: bytes)->str: return base64.b64encode(data).decode("ascii")
def b64d(text: str)->bytes: return base64.b64decode(text.encode("ascii"))
def log(msg: str)->None:
    line=f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {msg}"
    with LOG_FILE.open("a",encoding="utf-8") as f: f.write(line+"\n")
def load_json(path: Path, default: Any)->Any:
    try: return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception: return default
def save_json(path: Path, data: Any)->None:
    tmp=path.with_suffix(path.suffix+".tmp")
    tmp.write_text(json.dumps(data,indent=2),encoding="utf-8")
    tmp.replace(path)
def gh_path()->Path:
    candidates=[
        Path(os.environ.get("ProgramFiles",r"C:\Program Files"))/"GitHub CLI"/"gh.exe",
        Path(os.environ.get("LOCALAPPDATA",str(Path.home())))/"Programs"/"GitHub CLI"/"gh.exe",
    ]
    for p in candidates:
        if p.exists(): return p
    raise RuntimeError("GitHub CLI not found")
def gh_api(args: list[str], input_json: Any|None=None, timeout: int=30)->Any:
    cmd=[str(gh_path()),"api",*args]
    stdin=None
    if input_json is not None:
        cmd.extend(["--input","-"])
        stdin=json.dumps(input_json)
    r=subprocess.run(cmd,input=stdin,text=True,capture_output=True,timeout=timeout,
                     creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
    if r.returncode!=0: raise RuntimeError((r.stderr or r.stdout or "gh api failed")[-1200:])
    text=r.stdout.strip()
    return json.loads(text) if text else {}
def fetch_comments()->list[dict]:
    data=gh_api([f"repos/{REPO}/issues/{ISSUE}/comments?per_page=100"])
    return data if isinstance(data,list) else []
def post_comment(body: str)->dict:
    return gh_api(["-X","POST",f"repos/{REPO}/issues/{ISSUE}/comments"],{"body":body})
def load_private()->X25519PrivateKey:
    if KEY_FILE.exists():
        raw=b64d(KEY_FILE.read_text(encoding="ascii").strip())
        return X25519PrivateKey.from_private_bytes(raw)
    key=X25519PrivateKey.generate()
    raw=key.private_bytes(serialization.Encoding.Raw,serialization.PrivateFormat.Raw,serialization.NoEncryption())
    KEY_FILE.write_text(b64e(raw),encoding="ascii")
    try: os.chmod(KEY_FILE,0o600)
    except Exception: pass
    return key
def public_b64(key: X25519PrivateKey)->str:
    raw=key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
    return b64e(raw)
def derive(shared: bytes, node: str, cmd_id: str, purpose: bytes)->bytes:
    salt=hashlib.sha256(f"{node}:{cmd_id}".encode()).digest()
    return HKDF(algorithm=SHA256(),length=32,salt=salt,info=purpose).derive(shared)
def node_id(state: dict)->str:
    node=str(state.get("node") or "").strip()
    if not node:
        node="vbdc-"+secrets.token_hex(6)
        state["node"]=node
    return node
async def call_mcp(tool: str, arguments: dict)->dict:
    async with streamablehttp_client(MCP_URL) as (read,write,_):
        async with ClientSession(read,write) as s:
            await s.initialize()
            listed=await s.list_tools()
            names={t.name for t in listed.tools}
            if tool not in names: raise ValueError("unknown VexBridge tool")
            result=await s.call_tool(tool,arguments)
            items=[]
            for item in result.content:
                if hasattr(item,"model_dump"): items.append(item.model_dump(mode="json"))
                else: items.append({"type":getattr(item,"type","unknown"),"text":getattr(item,"text",str(item))})
            return {"ok":not bool(getattr(result,"isError",False)),"content":items,
                    "structuredContent":getattr(result,"structuredContent",None)}
def parse_envelope(body: str)->dict|None:
    marker="VEXBRIDGE_CMD\n"
    if not body.startswith(marker): return None
    raw=body[len(marker):].strip()
    if raw.startswith("```"): raw=raw.split("\n",1)[1].rsplit("```",1)[0].strip()
    data=json.loads(raw)
    return data if isinstance(data,dict) else None
def decrypt_command(priv: X25519PrivateKey, env: dict, node: str)->tuple[dict,bytes]:
    if int(env.get("v",0))!=1 or str(env.get("node"))!=node: raise ValueError("envelope target/version mismatch")
    cmd_id=str(env.get("id") or "")
    if not cmd_id or len(cmd_id)>100: raise ValueError("invalid command id")
    peer=X25519PublicKey.from_public_bytes(b64d(str(env["epk"])))
    shared=priv.exchange(peer)
    key=derive(shared,node,cmd_id,b"vexbridge-command-v1")
    aad=f"vexbridge-command-v1:{node}:{cmd_id}".encode()
    plain=AESGCM(key).decrypt(b64d(str(env["nonce"])),b64d(str(env["ciphertext"])),aad)
    payload=json.loads(plain.decode("utf-8"))
    now=time.time()
    created=float(payload.get("created_at",0)); expires=float(payload.get("expires_at",0))
    if created>now+120 or expires<now or expires-created>1800: raise ValueError("expired command")
    return payload,shared
def encrypted_result(shared: bytes, node: str, cmd_id: str, result: dict)->list[str]:
    raw=json.dumps({"v":1,"id":cmd_id,"node":node,"at":time.time(),"result":result},
                   ensure_ascii=False,separators=(",",":")).encode("utf-8")
    packed=zlib.compress(raw,9)
    key=derive(shared,node,cmd_id,b"vexbridge-result-v1")
    nonce=os.urandom(12)
    aad=f"vexbridge-result-v1:{node}:{cmd_id}".encode()
    data=b64e(AESGCM(key).encrypt(nonce,packed,aad))
    pieces=[data[i:i+38000] for i in range(0,len(data),38000)] or [""]
    out=[]
    for i,piece in enumerate(pieces,1):
        env={"v":1,"id":cmd_id,"node":node,"nonce":b64e(nonce),"part":i,"parts":len(pieces),"data":piece}
        out.append("VEXBRIDGE_RESULT\n```json\n"+json.dumps(env,separators=(",",":"))+"\n```")
    return out
def announce_key(comments: list[dict], priv: X25519PrivateKey, node: str)->None:
    pub=public_b64(priv)
    for c in comments:
        body=str(c.get("body") or "")
        if body.startswith("VEXBRIDGE_PUBLIC_KEY\n"):
            try:
                data=json.loads(body.split("\n",1)[1].strip().replace("```json","").replace("```","").strip())
                if data.get("node")==node and data.get("public_key")==pub: return
            except Exception: pass
    body="VEXBRIDGE_PUBLIC_KEY\n```json\n"+json.dumps({"v":1,"node":node,"public_key":pub},separators=(",",":"))+"\n```"
    post_comment(body)
def handle_comment(comment: dict, priv: X25519PrivateKey, node: str)->None:
    if str((comment.get("user") or {}).get("login") or "").lower()!=OWNER.lower(): return
    env=parse_envelope(str(comment.get("body") or ""))
    if not env or str(env.get("node"))!=node: return
    cmd_id=str(env.get("id") or "")
    try:
        payload,shared=decrypt_command(priv,env,node)
        tool=str(payload.get("tool") or "")
        arguments=payload.get("arguments") or {}
        if not isinstance(arguments,dict): raise ValueError("arguments must be an object")
        result=asyncio.run(call_mcp(tool,arguments))
    except Exception as exc:
        try:
            peer=X25519PublicKey.from_public_bytes(b64d(str(env["epk"])))
            shared=priv.exchange(peer)
            result={"ok":False,"error":f"{type(exc).__name__}: {exc}"[:2000]}
        except Exception:
            log(f"unreplyable command {cmd_id}: {type(exc).__name__}: {exc}")
            return
    for body in encrypted_result(shared,node,cmd_id,result): post_comment(body)
def write_status(node: str, state: dict, ok: bool=True, error: str|None=None)->None:
    save_json(STATUS_FILE,{"running":True,"node":node,"ok":ok,"last_poll":time.time(),
                           "last_comment_id":state.get("last_comment_id",0),"error":error})
def main()->int:
    state=load_json(STATE_FILE,{})
    node=node_id(state); priv=load_private()
    comments=fetch_comments()
    announce_key(comments,priv,node)
    if not state.get("initialized"):
        state["last_comment_id"]=max([int(c.get("id",0)) for c in comments] or [0])
        state["initialized"]=True; save_json(STATE_FILE,state)
    log(f"relay started node={node}")
    while True:
        try:
            comments=fetch_comments()
            last=int(state.get("last_comment_id",0))
            fresh=[c for c in comments if int(c.get("id",0))>last]
            for c in sorted(fresh,key=lambda x:int(x.get("id",0))):
                handle_comment(c,priv,node)
                state["last_comment_id"]=max(int(state.get("last_comment_id",0)),int(c.get("id",0)))
                save_json(STATE_FILE,state)
            write_status(node,state,True,None)
        except Exception as exc:
            log(f"poll error {type(exc).__name__}: {exc}")
            write_status(node,state,False,f"{type(exc).__name__}: {exc}"[:500])
        time.sleep(POLL_SECONDS)
if __name__=="__main__":
    raise SystemExit(main())
