from .models import loja_do_usuario


def marketplace(request):
    """Disponibiliza a loja do usuário logado (se for lojista) em todos os templates."""
    return {"loja_usuario": loja_do_usuario(getattr(request, "user", None))}
