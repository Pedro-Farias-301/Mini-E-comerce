from rest_framework.permissions import SAFE_METHODS, BasePermission

from ..models import loja_do_usuario


class EhLojistaOuAdmin(BasePermission):
    """Usuário autenticado que é administrador (staff) ou dono de uma loja no marketplace."""

    message = "Acesso restrito a lojistas do marketplace ou administradores."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and (user.is_staff or loja_do_usuario(user)))


class EhDonoDoProdutoOuSomenteLeitura(BasePermission):
    """
    - Leitura (GET/HEAD/OPTIONS): liberada para qualquer pessoa (catálogo público).
    - Criação: apenas lojistas ou administradores.
    - Alteração/remoção: apenas o lojista dono do produto ou um administrador.
    """

    message = "Apenas o lojista dono do produto (ou um administrador) pode alterá-lo."

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return EhLojistaOuAdmin().has_permission(request, view)

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        if request.user.is_staff:
            return True
        loja = loja_do_usuario(request.user)
        return loja is not None and obj.loja_id == loja.pk
