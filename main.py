import os
import openai
from io import StringIO
import sys

openai.api_key = os.getenv("OPENAI_KEY")

# TODO: could implement timeouts for gpt-3.5-turbo, because by default you will get rate limited to 3 requests per minute. gpt-4 is slow enough that you probably won't hit that.
def chat(messages, model="gpt-4", temperature=0.7):
    """actually sends the request out"""
    completion = openai.ChatCompletion.create(
        model=model,
        messages=messages,
        temperature=temperature
    )
    return completion.choices[0].message["content"]

def verifier(summary, proposed_output):
    messages = [
        {"role": "system", "content": "Be accurate, brief, and friendly. Respond LGTM if it looks good (with no further commentary), or FIXME if it needs improvement."},
        {"role": "user", "content": f"Verify if this is a good solution that fulfills all the requirements in the instructions: {summary}\n\n | Proposed solution: \n\n{proposed_output}"}
    ]
    response = chat(messages, temperature=0)
    return response

def generate_code(nl_instructions):
    """nl_instructions stands for natural language instructions."""
    code_system_message = "Generate python code and comments, with NO further natural language description or preamble. The output should be executable directly, in other words. Only generate code you can pipe directly into a python interpreter. Don't include stuff like if __name__ == \"__main__\" Don't include backticks."
    messages = [
        {"role": "system", "content": code_system_message},
        {"role": "user", "content": nl_instructions}
    ]

    for i in range(5):
        response = chat(messages)

        # really stupid edge case where gpt-4 still cannot figure out how to avoid backticks
        print(f"proposed generated code: {response[:15]}...{response[-15:]}")
        response = response.strip()
        if response.startswith("```python\n"):
            response = response[10:]
        elif response.startswith("```\n"): # backticks without the python label
            response = response[4:]
        while response.endswith("```"):
            response = response[:-3]
            response = response.strip() # bafflingly it produces TWO sets of backticks by default fairly consistently. i have no idea why it does this

        verification = verifier(f"system message: {code_system_message}, nl_instructions: {nl_instructions}", f"response: {response}")
        if verification.startswith("LGTM"):
            return response
        elif verification.startswith("FIXME"):
            messages.append({"role": "user", "content": verification})
        else:
            messages.append({"role": "user", "content": "Please try again."})
    raise AssertionError("Human help needed. Latest attempt: " + response)

def analyze_data(filename, description=None):
    """Analyze data in a file using GPT-generated code."""

    def inspect_data_code(filename):
        nl_instructions = f"Generate Python code to inspect the data in the file '{filename}' and get a rough idea of its format (e.g., CSV, JSON, or raw text). The code should read the file and print a sample of its content. The file might be quite large, so be sure to generate a solution that doesn't require the entire file for initial inspection."
        code = generate_code(nl_instructions)
        return code

    def explore_data_code(filename, data_summary):
        nl_instructions = f"Generate Python code to explore that dataset in {filename}. Here's what we think is true about the data: {data_summary}. Let's look at some basic statistics, possible missing data (e.g. pandas.info or something), and possible visualizations. Provide suggestions for further analysis. You may use the python libraries pandas, matplotlib, and numpy."
        code = generate_code(nl_instructions)
        return code

    def exec_capture_output(code, globals_dict):
        old_stdout = sys.stdout
        sys.stdout = StringIO()
        try:
            exec(code, globals_dict)
            return sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout

    # Inspect data
    print(f"Inspecting data from filename {filename}...")
    inspect_code = inspect_data_code(filename)
    inspect_output = exec_capture_output(inspect_code, globals())

    # Determine data format
    messages = [
        {"role": "system", "content": "Provide brief details about the data, including its format, a brief summary of the contents, and if it's tabular data, the column names in a comma-separated list and an example of a row. If it's JSON or raw text, provide a short sample"},
        {"role": "user", "content": f"Given inspection code {inspect_code}, analyze output e.g. what type of file it is, etc: {inspect_output}"}
    ]
    data_summary = chat(messages)
    print("Data summary: " + data_summary)

    # Explore data
    exploration_code = explore_data_code(filename, data_summary)
    explore_output = exec_capture_output(exploration_code, globals())

    # Extract results of exploration
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": f"Given exploration code {exploration_code}, summarize your initial thoughts based on the output: {explore_output}"}
    ]
    results = chat(messages)

    # Display results
    print("Results: ", results)

    # Await user input for further analysis
    while True:
        user_input = input("Enter your request for further analysis or type 'quit' to exit: ")
        if user_input.lower() == "quit":
            break
        else:
            code = generate_code(f"{user_input}. The filename is {filename}.")
            exec(code, globals())

# Test the analyze_data function
analyze_data("file.csv")