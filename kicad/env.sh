# Normally in /etc/profile.d/kicad-env.sh
# ---
# Env var for kicad github plugin
export KIGITHUB="https://github.com/KiCad"
# Env var for kicad pcbnew plugins
export KICAD_PATH=/usr/share/kicad

# For library-repos-install.sh script at 'https://raw.githubusercontent.com/KiCad/kicad-source-mirror/master/scripts/library-repos-install.sh'
export WORKING_TREES=~/.kicad/sources
export KISYSMOD=$WORKING_TREES/library-repos
