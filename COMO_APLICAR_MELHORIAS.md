# Como Aplicar as Melhorias no Main

## 🔄 Situação Atual

As melhorias implementadas estão na branch `claude/fix-web-scraping-data-3H2ic`, mas **NÃO foram aplicadas no `main`** ainda.

### O que está na branch de fix:
✅ URLs corrigidas (sem www)
✅ Sistema de fallback inteligente
✅ Headers HTTP realistas + sessões
✅ Timeouts progressivos
✅ Tratamento robusto de erros
✅ Priorização de datas conhecidas

### O que está no main:
❌ Código antigo (com URLs erradas)
❌ Sem fallback
❌ Headers simples

**Por isso o GitHub Actions não está funcionando** - ele executa o código do `main` que ainda tem problemas!

---

## 🚀 Aplicar as Melhorias (Opção 1: Pull Request)

### 1. Criar Pull Request

Vá para: https://github.com/tadeugomes/balneabilidade/compare/main...claude/fix-web-scraping-data-3H2ic

Ou acesse:
1. https://github.com/tadeugomes/balneabilidade/pulls
2. Clique em **"New pull request"**
3. Base: `main` ← Compare: `claude/fix-web-scraping-data-3H2ic`
4. Clique em **"Create pull request"**

### 2. Revisar as Mudanças

O PR vai mostrar:
- 5 commits com melhorias
- Arquivos modificados: `etl/fetch_sema.py` e documentação
- +300 linhas adicionadas, ~50 removidas

### 3. Merge do PR

Clique em **"Merge pull request"** → **"Confirm merge"**

### 4. Aguardar Deploy

Após o merge:
- GitHub Actions será acionado automaticamente (push no main)
- O workflow vai executar com o código corrigido
- Se conseguir acessar o servidor SEMA, vai atualizar os dados
- Deploy automático para GitHub Pages

---

## 🚀 Aplicar as Melhorias (Opção 2: Merge Direto via Git)

Se preferir fazer via terminal:

```bash
# 1. Certifique-se de estar atualizado
git fetch origin

# 2. Ir para o main
git checkout main
git pull origin main

# 3. Fazer merge da branch de fix
git merge claude/fix-web-scraping-data-3H2ic

# 4. Resolver conflitos (se houver)
# Provavelmente não haverá conflitos

# 5. Push para o repositório
git push origin main
```

**IMPORTANTE**: Após o push, o GitHub Actions vai executar automaticamente!

---

## 🚀 Aplicar as Melhorias (Opção 3: Squash Merge)

Se quiser um histórico mais limpo:

```bash
git checkout main
git pull origin main
git merge --squash claude/fix-web-scraping-data-3H2ic
git commit -m "feat: Implementa melhorias completas no sistema de scraping

- Corrige URLs (remove www)
- Adiciona sistema de fallback inteligente
- Melhora headers HTTP e sessões
- Implementa timeouts progressivos
- Prioriza datas conhecidas
- Adiciona documentação completa

Resolve problema de bloqueio de IPs pelo servidor SEMA.
Implementa alternativas para atualização manual."

git push origin main
```

---

## ⚠️ O que vai acontecer após o merge

### 1. **GitHub Actions vai executar automaticamente**

Quando você fizer push/merge no `main`, o workflow será acionado por este trigger:

```yaml
on:
  push:
    branches: [ main, master ]
```

### 2. **Três cenários possíveis:**

#### ✅ **Cenário A: Sucesso Total**
- Scraping funciona
- Dados atualizados
- Commit automático gerado
- Site atualizado

#### ⚠️ **Cenário B: Sucesso Parcial**
- Scraping funciona parcialmente
- Alguns PDFs baixados
- Dados podem ou não ser mais recentes que 17/11/2025
- Site atualizado com o que conseguiu

#### ❌ **Cenário C: Falha (Bloqueio continua)**
- IP do GitHub Actions ainda bloqueado (erro 503)
- Sistema de fallback tenta URLs diretas
- Todos os PDFs falham com 503
- Nenhum dado novo
- Workflow completa sem erro (devido a `continue-on-error: true`)
- **Nenhum commit gerado** (porque não houve mudanças)

---

## 🔍 Como Verificar o Resultado

### 1. **Aguardar 2-3 minutos após o push**

### 2. **Verificar execução:**
https://github.com/tadeugomes/balneabilidade/actions

### 3. **Ver os logs:**
Clique na execução → "build-and-deploy" → Expandir steps

### 4. **Verificar se houve commit:**
```bash
git fetch origin main
git log origin/main -3
```

Procure por: `chore(data): auto-update points.json [skip ci]`

### 5. **Verificar o site:**
https://tadeugomes.github.io/balneabilidade/

Limpe o cache: `Ctrl + Shift + R` (Windows) ou `Cmd + Shift + R` (Mac)

---

## 📊 Comparação: Antes vs Depois do Merge

### **Antes (main atual):**
```python
# URLs erradas
LAUDOS_URL = 'https://www.sema.ma.gov.br/...'  # ❌ Com www (bloqueado)

# Sem fallback
items = fetch_laudo_index()  # ❌ Falha e para

# Headers simples
headers = {'User-Agent': 'BalneabilidadeBot'}  # ❌ Facilmente bloqueado
```

### **Depois (após merge):**
```python
# URLs corretas
LAUDOS_URL = 'https://sema.ma.gov.br/...'  # ✅ Sem www

# Com fallback
items = fetch_laudo_index()
if not items:
    items = generate_recent_pdf_urls()  # ✅ Tenta URLs diretas

# Headers realistas + sessão
session = requests.Session()
headers = {
    'User-Agent': 'Mozilla/5.0 ...',  # ✅ Parece navegador real
    'Accept': '...',
    'Accept-Language': 'pt-BR,pt;q=0.9',
    # ... mais headers
}
```

---

## 🎯 Recomendação

**FAÇA O MERGE AGORA** para:

1. ✅ Aplicar as correções no main
2. ✅ Permitir que o GitHub Actions use o código corrigido
3. ✅ Ter a melhor chance de sucesso no scraping automático
4. ✅ Documentação atualizada disponível no repositório

**Mesmo que o GitHub Actions continue bloqueado**, você terá:
- Código correto disponível para execução local
- Scripts de processamento manual
- Documentação completa
- Sistema de fallback robusto

---

## ❓ FAQ

### **P: E se houver conflitos no merge?**
R: Improvável, mas se houver, escolha as mudanças da branch `claude/fix-web-scraping-data-3H2ic`

### **P: Posso testar antes de fazer merge?**
R: Sim! Execute localmente:
```bash
git checkout claude/fix-web-scraping-data-3H2ic
python etl/fetch_sema.py --limit 3 --timeout 60
```

### **P: E se o merge quebrar algo?**
R: Você pode reverter:
```bash
git revert HEAD
git push origin main
```

### **P: Preciso esperar quinta-feira para o workflow executar?**
R: Não! O push no main acionará imediatamente. Mas você também pode forçar manualmente em Actions.

---

**Última atualização**: 09/02/2026
**Status**: Melhorias prontas, aguardando merge no main
