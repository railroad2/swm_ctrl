#!/bin/bash

set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
upload_list="$script_dir/UPLOADLIST"

while IFS= read -r filename; do
    [[ -z "$filename" ]] && continue

    mpremote cp "$script_dir/$filename" :
done < "$upload_list"
