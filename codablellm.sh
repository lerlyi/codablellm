#!/bin/bash

# Get the script's current directory
script_directory=$(dirname "$(realpath "$0")")

# Initialize an array to store updated arguments for Docker
updated_args=()

# Process each argument (file or directory)
for arg in "$@"; do
    # If the argument starts with '--', it's a flag (e.g., --help) or a non-file argument (e.g., arg1)
    if [[ ! -e "$arg" ]]; then
        # If it's a flag or a non-file argument, just add it to updatedArgs as-is
        echo "Adding argument '$arg' to arguments."
        updated_args+=("$arg")
    else
        # Get the file name
        filename=$(basename "$arg")
        destination_path="$script_directory/$filename"

        # If the file is not already in the current directory, copy it
        if [[ "$arg" != "$destination_path" ]]; then
            if [[ ! -e "$destination_path" ]]; then
                echo "Copying '$arg' to '$destination_path'..."
                cp "$arg" "$destination_path"
            else
                echo "'$arg' already exists in the script directory. Skipping."
            fi
        fi

        # Add the destination path (relative to the script directory) to the updated arguments
        updated_args+=("./$filename")
    fi
done

# Print the updated arguments (for debugging)
echo "Updated Arguments: ${updated_args[@]}"

# Run the container for the app using docker-compose with updated arguments
docker-compose run --rm app codablellm "${updated_args[@]}"
