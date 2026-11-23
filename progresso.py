"""Barra de progresso no terminal e numa mensagem do Telegram que se atualiza."""
import sys
import time

LARGURA = 20


def barra(pct, largura=LARGURA):
    cheio = int(round(pct / 100 * largura))
    return "█" * cheio + "░" * (largura - cheio)


class Progresso:
    """atualizar(pct, etapa) desenha a barra; o Telegram é atualizado no máximo a cada 3 s."""

    def __init__(self, titulo, enviar=None, editar=None, intervalo=3.0):
        self.titulo = titulo
        self.enviar = enviar      # função(texto) -> message_id
        self.editar = editar      # função(message_id, texto)
        self.intervalo = intervalo
        self.msg_id = None
        self.ultimo_envio = 0.0
        self.ultimo_texto = ""
        self.ultimo_pct_log = -10
        self.tty = sys.stdout.isatty()
        self.pct = 0.0

    def atualizar(self, pct, etapa, forcar=False):
        pct = max(self.pct, min(100.0, pct))  # nunca volta para trás
        self.pct = pct
        # Terminal
        linha = f"[{barra(pct)}] {pct:3.0f}%  {etapa}"
        if self.tty:
            print("\r" + linha[:100].ljust(100), end="", flush=True)
            if pct >= 100:
                print()
        elif pct - self.ultimo_pct_log >= 10 or pct >= 100:  # log: uma linha a cada 10%
            print(linha, flush=True)
            self.ultimo_pct_log = pct
        # Telegram
        if not self.enviar:
            return
        texto = f"{self.titulo}\n{barra(pct, 16)} {pct:.0f}%\n{etapa}"
        agora = time.time()
        if texto == self.ultimo_texto:
            return
        if not forcar and pct < 100 and agora - self.ultimo_envio < self.intervalo:
            return
        try:
            if self.msg_id is None:
                self.msg_id = self.enviar(texto)
            else:
                self.editar(self.msg_id, texto)
            self.ultimo_texto, self.ultimo_envio = texto, agora
        except Exception as e:  # a barra nunca derruba o trabalho
            print(f"\n(aviso: não consegui atualizar a barra no Telegram: {e})")

    def faixa(self, inicio, fim):
        """Sub-barra: mapeia 0–100 de uma etapa para o trecho [inicio, fim] da barra geral."""
        return lambda p, etapa, forcar=False: self.atualizar(inicio + (fim - inicio) * p / 100, etapa, forcar)


class SemProgresso(Progresso):
    def __init__(self):
        super().__init__("")

    def atualizar(self, pct, etapa, forcar=False):
        pass
