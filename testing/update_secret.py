import os, sys, json, base64

# Ensure requests and pynacl are installed
try:
    import requests
    from nacl import public
except Exception:
    import subprocess
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', '--quiet', 'requests', 'pynacl'])
    import requests
    from nacl import public

repo = 'Prashant-Ai-Dev-spec/J.A.R.V.I.S'
headers = {'Authorization': f"token {os.environ.get('GITHUB_TOKEN')}", 'Accept': 'application/vnd.github.v3+json'}

# Get public key for repo
r = requests.get(f'https://api.github.com/repos/{repo}/actions/secrets/public-key', headers=headers)
if r.status_code != 200:
    print('FAILED_GET_KEY', r.status_code, r.text)
    sys.exit(2)
key_info = r.json()
public_key = key_info['key']
key_id = key_info['key_id']

# Encrypt NEW_TOKEN using the repo public key
new_token = os.environ.get('NEW_TOKEN')
if not new_token:
    print('NO_NEW_TOKEN')
    sys.exit(3)

public_key_bytes = base64.b64decode(public_key)
pk = public.PublicKey(public_key_bytes)
sealed_box = public.SealedBox(pk)
encrypted = sealed_box.encrypt(new_token.encode())
encrypted_value = base64.b64encode(encrypted).decode()

payload = {'encrypted_value': encrypted_value, 'key_id': key_id}
put = requests.put(f'https://api.github.com/repos/{repo}/actions/secrets/JARVIS_MCP_TOKEN', headers=headers, data=json.dumps(payload))
if put.status_code in (201, 204):
    print('SECRET_UPDATED')
    sys.exit(0)
else:
    print('FAILED_PUT', put.status_code, put.text)
    sys.exit(4)
