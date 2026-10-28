"""Benchmark prompts copied from the pinned protocol.

IFBench and GPQA get no system message. LCB uses the official generic
system message from LiveCodeBench / EvalScope 1.14.1. Nothing here is a
Friday persona, memory, or tool instruction.
"""

SYSTEM_LCB = (
    "You are an expert Python programmer. You will be given a question "
    "(problem specification) and will generate a correct Python program that "
    "matches the specification and passes all tests. You will NOT return "
    "anything except for the program."
)

FORMATTING_WITH_STARTER = (
    "You will use the following starter code to write the solution to the "
    "problem and enclose your code within delimiters."
)

FORMATTING_WITHOUT_STARTER = (
    "Read the inputs from stdin solve the problem and write the answer to "
    "stdout (do not directly test on the sample inputs). Enclose your code "
    "within delimiters as follows."
)

GPQA_TEMPLATE = (
    "Answer the following multiple choice question. The last line of your "
    "response should be of the following format: 'ANSWER: [LETTER]' "
    "(without quotes) where [LETTER] is one of {letters}. Think step by step "
    "before answering.\n\n{question}\n\n{choices}"
)


def lcb_format_prompt(starter_code: str) -> str:
    if starter_code:
        return (
            f"### Format: {FORMATTING_WITH_STARTER}\n"
            f"```python\n{starter_code}\n```\n\n"
        )
    return (
        f"### Format: {FORMATTING_WITHOUT_STARTER}\n"
        "```python\n# YOUR CODE HERE\n```\n\n"
    )


def lcb_user(question: str, starter_code: str) -> str:
    formatted = lcb_format_prompt(starter_code or "")
    return (
        f"### Question:\n{question}\n\n{formatted}"
        " ### Answer: (use the provided format with backticks)\n\n"
    )


def gpqa_user(question: str, choices: list[str]) -> str:
    rendered = "\n".join(f"{chr(65 + i)}) {text}" for i, text in enumerate(choices))
    letters = ",".join(chr(65 + i) for i in range(len(choices)))
    return GPQA_TEMPLATE.format(letters=letters, question=question, choices=rendered)


def prompt_fingerprint_material() -> dict:
    return {
        "ifbench": "user_prompt_only",
        "gpqa_template": GPQA_TEMPLATE,
        "lcb_system": SYSTEM_LCB,
        "lcb_format_with": FORMATTING_WITH_STARTER,
        "lcb_format_without": FORMATTING_WITHOUT_STARTER,
        "lcb_user_pattern": "### Question:\\n{q}\\n\\n{format} ### Answer: (use the provided format with backticks)\\n\\n",
    }
