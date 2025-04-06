# Get the script's current directory
$scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Definition

# Initialize an array to store updated arguments for Docker
$updatedArgs = @()

# Process each argument (file or directory)
foreach ($arg in $args) {
    # If the argument is a flag (e.g., --help) or a non-file argument (e.g., arg1), just add it to updatedArgs as is
    if ((Test-Path $arg -PathType Leaf -ErrorAction SilentlyContinue) -eq $false) {
        Write-Host "Adding argument '$arg' to arguments."
        $updatedArgs += $arg
    } else {
        # Get the full absolute path of the argument
        $filePath = Resolve-Path -Path $arg -ErrorAction SilentlyContinue

        # Check if the file or directory exists
        if (Test-Path $filePath) {
            # Check if the file is already in the script directory
            $destinationPath = Join-Path -Path $scriptDirectory -ChildPath (Split-Path -Leaf $filePath)

            if ($filePath -ne $destinationPath) {
                # If the file is not already in the script directory, copy it
                if (-not (Test-Path $destinationPath)) {
                    Write-Host "Copying '$filePath' to '$destinationPath'..."
                    Copy-Item -Path $filePath -Destination $destinationPath
                } else {
                    Write-Host "'$filePath' already exists in the script directory. Skipping."
                }

                # Add the destination path (relative to the script directory) to the updated arguments
                $updatedArgs += "./" + (Split-Path -Leaf $filePath)
            } else {
                Write-Host "'$filePath' is already in the script directory. Skipping."
                # If the file is already in the script directory, add it as-is to the updated arguments
                $updatedArgs += "./" + (Split-Path -Leaf $filePath)
            }
        } else {
            Write-Host "The file or directory '$filePath' does not exist. Skipping."
            # If the file or directory doesn't exist, add the original argument as-is
            $updatedArgs += $arg
        }
    }
}

# Print the updated arguments (for debugging)
Write-Host "Updated Arguments: $($updatedArgs -join ', ')"

# Run the container for the app using docker-compose with updated arguments
docker-compose run --rm app codablellm @updatedArgs
