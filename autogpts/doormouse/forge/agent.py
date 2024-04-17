import json
import pprint

from forge.actions import ActionRegister
from forge.sdk import (
    Agent,
    AgentDB,
    ForgeLogger,
    Step,
    StepRequestBody,
    Task,
    TaskRequestBody,
    Workspace,
)

from forge.llm import chat_completion_request
from forge.sdk import PromptEngine

LOG = ForgeLogger(__name__)


class ForgeAgent(Agent):
    """
    The goal of the Forge is to take care of the boilerplate code, so you can focus on
    agent design.

    There is a great paper surveying the agent landscape: https://arxiv.org/abs/2308.11432
    Which I would highly recommend reading as it will help you understand the possabilities.

    Here is a summary of the key components of an agent:

    Anatomy of an agent:
         - Profile
         - Memory
         - Planning
         - Action

    Profile:

    Agents typically perform a task by assuming specific roles. For example, a teacher,
    a coder, a planner etc. In using the profile in the llm prompt it has been shown to
    improve the quality of the output. https://arxiv.org/abs/2305.14688

    Additionally, based on the profile selected, the agent could be configured to use a
    different llm. The possibilities are endless and the profile can be selected
    dynamically based on the task at hand.

    Memory:

    Memory is critical for the agent to accumulate experiences, self-evolve, and behave
    in a more consistent, reasonable, and effective manner. There are many approaches to
    memory. However, some thoughts: there is long term and short term or working memory.
    You may want different approaches for each. There has also been work exploring the
    idea of memory reflection, which is the ability to assess its memories and re-evaluate
    them. For example, condensing short term memories into long term memories.

    Planning:

    When humans face a complex task, they first break it down into simple subtasks and then
    solve each subtask one by one. The planning module empowers LLM-based agents with the ability
    to think and plan for solving complex tasks, which makes the agent more comprehensive,
    powerful, and reliable. The two key methods to consider are: Planning with feedback and planning
    without feedback.

    Action:

    Actions translate the agent's decisions into specific outcomes. For example, if the agent
    decides to write a file, the action would be to write the file. There are many approaches you
    could implement actions.

    The Forge has a basic module for each of these areas. However, you are free to implement your own.
    This is just a starting point.
    """

    def __init__(self, database: AgentDB, workspace: Workspace):
        """
        The database is used to store tasks, steps and artifact metadata. The workspace is used to
        store artifacts. The workspace is a directory on the file system.

        Feel free to create subclasses of the database and workspace to implement your own storage
        """
        super().__init__(database, workspace)
        self.abilities = ActionRegister(self)

    async def create_task(self, task_request: TaskRequestBody) -> Task:
        """
        The agent protocol, which is the core of the Forge, works by creating a task and then
        executing steps for that task. This method is called when the agent is asked to create
        a task.

        We are hooking into function to add a custom log message. Though you can do anything you
        want here.
        """
        task = await super().create_task(task_request)
        LOG.info(
            f"📦 Task created: {task.task_id} input: {task.input[:40]}{'...' if len(task.input) > 40 else ''}"
        )
        return task

    async def execute_step(self, task_id: str, step_request: StepRequestBody) -> Step:
        """
        For a tutorial on how to add your own logic please see the offical tutorial series:
        https://aiedge.medium.com/autogpt-forge-e3de53cc58ec

        The agent protocol, which is the core of the Forge, works by creating a task and then
        executing steps for that task. This method is called when the agent is asked to execute
        a step.

        The task that is created contains an input string, for the benchmarks this is the task
        the agent has been asked to solve and additional input, which is a dictionary and
        could contain anything.

        If you want to get the task use:

        ```
        task = await self.db.get_task(task_id)
        ```

        The step request body is essentially the same as the task request and contains an input
        string, for the benchmarks this is the task the agent has been asked to solve and
        additional input, which is a dictionary and could contain anything.

        You need to implement logic that will take in this step input and output the completed step
        as a step object. You can do everything in a single step or you can break it down into
        multiple steps. Returning a request to continue in the step output, the user can then decide
        if they want the agent to continue or not.
        """

        task = await self.db.get_task(task_id)

        step = await self.db.create_step(
            task_id=task_id, input=step_request, is_last=True
        )

        prompt_engine = PromptEngine("gpt-4-turbo")
        system_prompt = prompt_engine.load_prompt("system-format")

        task_kwargs = {
            "task": task.input,
            "abilities": self.abilities.list_abilities_for_prompt(),
        }

        # Load the task prompt with those parameters
        task_prompt = prompt_engine.load_prompt("task-step", **task_kwargs)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": task_prompt}
        ]

        try:
            # Set the parameters for the chat completion
            chat_completion_kwargs = {
                "messages": messages,
                "model": "gpt-4-turbo",
            }
            # Get the LLM's response and interpret it
            chat_response = await chat_completion_request(**chat_completion_kwargs)
            answer = json.loads(chat_response.choices[0].message.content)

            # Log the answer for reference
            LOG.info(pprint.pformat(answer))

        except json.JSONDecodeError as e:
            # Handle JSON decoding errors
            LOG.error(f"Can't decode chat response: {chat_response}")
        except Exception as e:
            # Handle other errors
            LOG.error(f"Can't get chat response: {e}")

        step.output = answer["thoughts"]["speak"]
        LOG.info(f"(step.output): {step.output}")

        ability = answer["ability"]
        if ability:
            output = await self.abilities.run_action(
                task_id, ability["name"], **ability["args"]
            )

            LOG.info(f"(ability output): {output}")

            step.output += "\n-----\n".join(output)

        # TODO surely this is a terrible idea
        return step

        # Writing to the workspace
        #self.workspace.write(task_id=task_id, path="output.txt", data=b"Washington D.C")

        # Where does this go? Is this just tracking that we made that output.txt file?
        # await self.db.create_artifact(
        #     task_id=task_id,
        #     step_id=step.step_id,
        #     file_name="output.txt",
        #     relative_path="",
        #     agent_created=True,
        # )

        # step.output = "Washington D.C"
        #
        # LOG.info(
        #     f"\t✅ Final Step completed: {step.step_id}. \n"
        #     + f"Output should be placeholder text Washington D.C. You'll need to \n"
        #     + f"modify execute_step to include LLM behavior. Follow the tutorial "
        #     + f"if confused. "
        # )
