"""Único lugar que conoce las clases concretas de juez. Lo importa solo la rama por defecto de run.py."""
from evals.jueces.claude import JuezClaude
from evals.jueces.falso import JuezFalso

CATALOGO = {"claude": JuezClaude, "falso": JuezFalso}
