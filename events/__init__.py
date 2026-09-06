"""The contract between the two services.

There is exactly one record that crosses the line between the signal board and
the agent system, and it is defined here, in a package that neither service
owns. That is deliberate: the moment one service owns the shape, the other one
is a client rather than a peer, and changing it becomes a negotiation.

Write the contract before either side. It is the cheapest hour in the project.
"""
