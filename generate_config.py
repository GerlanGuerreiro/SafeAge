"""
generate_config.py
Gera frigate/config.yml substituindo variáveis do .env no template.
Execute sempre que mudar o .env ou a câmera.
"""
env = {}
with open('.env') as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            key, _, value = line.partition('=')
            env[key.strip()] = value.strip().strip('"').strip("'")

with open('frigate/config.camera.yml') as f:
    template = f.read()

for key, value in env.items():
    template = template.replace('{' + key + '}', value)

with open('frigate/config.yml', 'w') as f:
    f.write(template)

print("config.yml gerado:")
print(f"  Camera: rtsp://{env.get('CAMERA_USER')}:***@{env.get('CAMERA_HOST')}:{env.get('CAMERA_PORT')}/{env.get('CAMERA_ENDPOINT')}")
