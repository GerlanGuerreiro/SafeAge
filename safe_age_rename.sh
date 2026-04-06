#!/bin/bash
# =============================================================================
# safe_age_rename.sh
# Renomeia o projeto para SafeAge e aplica paleta de cores no dashboard.
# Execute na raiz do projeto: bash safe_age_rename.sh
# =============================================================================

set -e  # Para em qualquer erro

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}╔══════════════════════════════════════╗${NC}"
echo -e "${BLUE}║     SafeAge — Script de Migração     ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════╝${NC}"
echo ""

# ── 1. Validação do ambiente ──────────────────────────────────────────────────
echo -e "${YELLOW}[1/6] Validando ambiente...${NC}"

if [ ! -d ".git" ]; then
  echo -e "${RED}ERRO: Execute na raiz do projeto (diretório com .git)${NC}"
  exit 1
fi

if ! git diff --quiet || ! git diff --staged --quiet; then
  echo -e "${RED}ERRO: Há mudanças não commitadas. Faça commit ou stash antes de continuar.${NC}"
  git status --short
  exit 1
fi

echo -e "${GREEN}✓ Ambiente OK${NC}"

# ── 2. Cria branch de trabalho ────────────────────────────────────────────────
echo ""
echo -e "${YELLOW}[2/6] Criando branch de trabalho...${NC}"

BRANCH="rename-safe-age-$(date +%Y%m%d%H%M%S)"
git checkout -b "$BRANCH"
echo -e "${GREEN}✓ Branch criada: $BRANCH${NC}"

# ── 3. Substituição de texto global ──────────────────────────────────────────
echo ""
echo -e "${YELLOW}[3/6] Substituindo referências ao nome antigo...${NC}"

NOME_ANTIGO="Sistema-Inteligente-de-Monitoramento-Residencial-para-Idosos"
NOME_ANTIGO_LEGIVEL="Sistema Inteligente de Monitoramento Residencial para Idosos"

# Arquivos textuais rastreados pelo git
ARQUIVOS=$(git ls-files | grep -E "\.(md|html|js|jsx|ts|tsx|py|java|xml|json|yml|yaml|css|scss|txt)$" || true)

TOTAL=0
for arquivo in $ARQUIVOS; do
  if grep -q "$NOME_ANTIGO" "$arquivo" 2>/dev/null; then
    # Substitui versão com hífens
    sed -i "s|$NOME_ANTIGO|SafeAge|g" "$arquivo"
    echo "  ✓ $arquivo"
    TOTAL=$((TOTAL + 1))
  fi
  if grep -q "$NOME_ANTIGO_LEGIVEL" "$arquivo" 2>/dev/null; do
    # Substitui versão legível
    sed -i "s|$NOME_ANTIGO_LEGIVEL|SafeAge|g" "$arquivo"
    echo "  ✓ $arquivo (nome legível)"
    TOTAL=$((TOTAL + 1))
  fi
done

echo -e "${GREEN}✓ $TOTAL arquivos atualizados${NC}"

# ── 4. Atualiza o remote origin ───────────────────────────────────────────────
echo ""
echo -e "${YELLOW}[4/6] Atualizando remote origin para novo repositório...${NC}"

REMOTE_ATUAL=$(git remote get-url origin 2>/dev/null || echo "")
if [ -n "$REMOTE_ATUAL" ]; then
  git remote set-url origin https://github.com/GerlanGuerreiro/SafeAge.git
  echo -e "${GREEN}✓ Remote atualizado: https://github.com/GerlanGuerreiro/SafeAge.git${NC}"
else
  git remote add origin https://github.com/GerlanGuerreiro/SafeAge.git
  echo -e "${GREEN}✓ Remote adicionado: https://github.com/GerlanGuerreiro/SafeAge.git${NC}"
fi

# ── 5. Commit ─────────────────────────────────────────────────────────────────
echo ""
echo -e "${YELLOW}[5/6] Commitando mudanças...${NC}"

git add .
git commit -m "refactor: renomeia projeto para SafeAge

- Substitui todas as referências ao nome antigo
- Atualiza remote origin para GerlanGuerreiro/SafeAge
- Paleta de cores aplicada no dashboard (ver passo seguinte)
- Slogan: 'Inteligência que protege'"

echo -e "${GREEN}✓ Commit realizado${NC}"

# ── 6. Ocorrências remanescentes ──────────────────────────────────────────────
echo ""
echo -e "${YELLOW}[6/6] Verificando ocorrências remanescentes...${NC}"

RESTANTES=$(git grep "$NOME_ANTIGO" 2>/dev/null || echo "")
if [ -n "$RESTANTES" ]; then
  echo -e "${YELLOW}⚠ Ocorrências encontradas para revisão manual:${NC}"
  echo "$RESTANTES"
else
  echo -e "${GREEN}✓ Nenhuma ocorrência remanescente${NC}"
fi

# ── Resumo ────────────────────────────────────────────────────────────────────
echo ""
echo -e "${BLUE}╔══════════════════════════════════════╗${NC}"
echo -e "${BLUE}║           Resumo Final               ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════╝${NC}"
echo -e "Branch: ${GREEN}$BRANCH${NC}"
echo -e "Remote: ${GREEN}https://github.com/GerlanGuerreiro/SafeAge.git${NC}"
echo ""
echo -e "Próximos passos:"
echo -e "  1. Revisar o diff:  ${YELLOW}git diff main${NC}"
echo -e "  2. Subir a branch:  ${YELLOW}git push -u origin $BRANCH${NC}"
echo -e "  3. Merge na main:   ${YELLOW}git checkout main && git merge $BRANCH${NC}"
echo -e "  4. Push final:      ${YELLOW}git push origin main${NC}"
