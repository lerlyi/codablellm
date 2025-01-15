# Import required libraries
import json
from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import ConsoleTaskMonitor
import os

# Ensure an argument is provided
if len(getScriptArgs()) < 1:
    print("Usage: <script> <output_file_path>")
    exit(1)

# Get the output file path from the first argument
output_file = getScriptArgs()[0]

# Initialize decompiler
decompiler = DecompInterface()
decompiler.openProgram(currentProgram)

# Initialize result list
result_list = []

# Get the file name from the program's executable path
file_name = os.path.basename(currentProgram.getExecutablePath())

# Iterate over all functions in the current program
function_iter = currentProgram.getFunctionManager().getFunctions(True)
for function in function_iter:
    # Get the function name and entry point
    name = function.getName()
    entry_point = function.getEntryPoint().toString()

    # Get the path (module or file name)
    path = currentProgram.getExecutablePath()

    # Decompile the function
    decompiled_results = \
        decompiler.decompileFunction(function, 60, ConsoleTaskMonitor())
    if decompiled_results.decompileCompleted():
        definition = decompiled_results.getDecompiledFunction().getC()
    else:
        print("Decompilation failed")
        exit(1)

    # Get the assembly instructions
    instruction_iter = \
        currentProgram.getListing().getInstructions(function.getBody(), True)
    assembly = "\n".join([str(instr) for instr in instruction_iter])

    # Get the architecture (processor name)
    architecture = str(currentProgram.getLanguage().getProcessor())

    # Create a dictionary for this function
    func_dict = {
        "path": path,
        "definition": definition,
        "name": name,
        "assembly": assembly,
        "architecture": architecture
    }

    # Add the function dictionary to the result list
    result_list.append(func_dict)

# Dump the result list to the output file as JSON
with open(output_file, "w") as f:
    json.dump(result_list, f, indent=4)

print('Decompiled functions saved to' + output_file)
