#!/usr/bin/env bash
# Register the plugin for local development by symlinking src/ into Claude's plugin cache.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MARKETPLACE="${REPO_ROOT}/.claude-plugin/marketplace.json"
PLUGIN_VERSION=$(python3 -c "import json; print(json.load(open('${MARKETPLACE}'))['plugins'][0]['version'])")
MARKETPLACE_NAME="zimalabs"
CACHE_DIR="${HOME}/.claude/plugins/cache/${MARKETPLACE_NAME}/decision/${PLUGIN_VERSION}"
MARKETPLACE_DIR="${HOME}/.claude/plugins/marketplaces/${MARKETPLACE_NAME}"
PLUGIN_KEY="decision@${MARKETPLACE_NAME}"
INSTALLED_PLUGINS="${HOME}/.claude/plugins/installed_plugins.json"
KNOWN_MARKETPLACES="${HOME}/.claude/plugins/known_marketplaces.json"
SETTINGS="${HOME}/.claude/settings.json"

# Symlink source into cache and marketplace
rm -rf "${CACHE_DIR}"
mkdir -p "$(dirname "${CACHE_DIR}")"
ln -sfn "${REPO_ROOT}/src" "${CACHE_DIR}"
mkdir -p "${MARKETPLACE_DIR}/.claude-plugin"
cp "${MARKETPLACE}" "${MARKETPLACE_DIR}/.claude-plugin/marketplace.json"
ln -sfn "${REPO_ROOT}/src" "${MARKETPLACE_DIR}/src"

# Register in known_marketplaces.json
python3 -c "
import json, pathlib, datetime
km = pathlib.Path('${KNOWN_MARKETPLACES}')
data = json.loads(km.read_text()) if km.exists() else {}
data['${MARKETPLACE_NAME}'] = {
    'source': {'source': 'git', 'url': 'https://github.com/zimalabs/claude-decision-plugin.git'},
    'installLocation': '${MARKETPLACE_DIR}',
    'lastUpdated': datetime.datetime.now(datetime.timezone.utc).isoformat(),
}
km.write_text(json.dumps(data, indent=4) + '\n')
"

# Register in installed_plugins.json
python3 -c "
import json, pathlib, datetime
ip = pathlib.Path('${INSTALLED_PLUGINS}')
data = json.loads(ip.read_text()) if ip.exists() else {'version': 2, 'plugins': {}}
data['plugins']['${PLUGIN_KEY}'] = [{
    'scope': 'user',
    'installPath': '${CACHE_DIR}',
    'version': '${PLUGIN_VERSION}',
    'installedAt': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'lastUpdated': datetime.datetime.now(datetime.timezone.utc).isoformat(),
}]
ip.write_text(json.dumps(data, indent=4) + '\n')
"

# Enable in settings.json
python3 -c "
import json, pathlib
s = pathlib.Path('${SETTINGS}')
data = json.loads(s.read_text()) if s.exists() else {}
ep = data.setdefault('enabledPlugins', {})
ep['${PLUGIN_KEY}'] = True
s.write_text(json.dumps(data, indent=4) + '\n')
"

echo "Linked ${CACHE_DIR} → ${REPO_ROOT}/src"
echo "Registered ${PLUGIN_KEY} with marketplace, installed_plugins, and settings"
echo "Run /reload-plugins to activate"
