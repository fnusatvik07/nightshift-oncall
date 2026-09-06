"""Service one: the signal board, as a service rather than a command.

You already have `signals/board.py`. It works, and you run it by typing
`python cli.py board`. That is fine for a laptop and useless at 3am.

This package is the same idea, productionised:

    kpis.py        the catalogue. One KPI is one query returning one number
    evaluate.py    a KPI becomes a reading; a reading becomes a verdict
    store.py       every reading and every breach, kept
    api.py         an HTTP surface, so anything can ask
    scheduler.py   the clock, so nobody has to type
    emit.py        the one record it hands to the agent system

Read them in that order. Each one only needs the one before it.
"""
