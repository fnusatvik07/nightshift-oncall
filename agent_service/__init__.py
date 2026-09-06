"""Service two: the on call agent system.

Asleep until a record arrives. Then it does what a good engineer does at 3am,
without the fetching: works out whether the number really moved, what is wrong
with the rows, where the wrong value entered the platform, what the smallest
fix would be, and whether it worked.

    tools/       the toolbox, deliberately split so no agent can do everything
    agents.py    the five specialists, each with one question and a typed answer
    supervisor.py the main agent that holds the plan
    worker.py    the HTTP surface, so the signal board can ring the doorbell

It changes nothing. Every outcome is an artifact a person reads and decides on.
"""
