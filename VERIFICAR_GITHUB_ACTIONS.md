# Como Verificar o GitHub Actions

## 📊 Status Atual

**Branch main**:
- Total de pontos: 22
- Última data com dados: **17/11/2025** (há ~3 meses)
- Última atualização automática: 27/11/2025

**Situação**: O workflow executou mas **não atualizou** os dados, indicando que o scraping falhou.

---

## 🔍 Passo a Passo para Verificar os Logs

### 1. Acessar o GitHub Actions

Vá para: **https://github.com/tadeugomes/balneabilidade/actions**

### 2. Localizar a Execução Recente

Você verá uma lista de execuções do workflow "Update data and deploy". Procure por:
- ✅ Verde = Sucesso (mas pode ter falhado silenciosamente no ETL)
- ❌ Vermelho = Falha completa
- 🟡 Amarelo = Em execução

### 3. Clicar na Execução Mais Recente

Clique no nome da execução (ex: "Update data and deploy")

### 4. Abrir o Job "build-and-deploy"

Na página da execução, clique em **"build-and-deploy"** no painel esquerdo

### 5. Expandir o Step "Run ETL to refresh data"

Procure e clique no step:
```
▶ Run ETL to refresh data (limit=10)
```

### 6. Analisar os Logs

**O que procurar nos logs:**

#### ✅ **Cenário 1: Bloqueio de IP (503)**
```
WARN: falha ao acessar índice de laudos em https://sema.ma.gov.br/laudos-de-balneabilidade
ERROR: 503 Server Error: Service Unavailable
FALLBACK: Índice indisponível. Tentando URLs diretas...
WARN: falha ao baixar PDF ... 503 Server Error
```
**Causa**: GitHub Actions também está bloqueado pelo servidor SEMA
**Solução**: Executar localmente ou processar PDF manualmente

#### ✅ **Cenário 2: Timeout**
```
WARN: falha ao acessar ... Read timed out
HTTPSConnectionPool ... timeout=90
```
**Causa**: Servidor SEMA muito lento ou não respondendo
**Solução**: Aumentar timeout no workflow ou executar localmente

#### ✅ **Cenário 3: Nenhum Dado Extraído**
```
Aviso: nenhuma linha extraída dos PDFs
Possíveis causas:
  - Problemas de conectividade com o servidor da SEMA
  - PDFs com formato diferente do esperado
```
**Causa**: PDF baixado mas não conseguiu extrair dados
**Solução**: Verificar se o layout do PDF mudou

#### ✅ **Cenário 4: Sucesso Parcial**
```
SUCCESS: PDF baixado: Laudo_de_Balneabilidade_XX_XX_XXXX.pdf
Gerado: /home/runner/work/.../data/points.json (itens=22)
```
**Se vir isso**: O scraping funcionou! Mas pode não ter encontrado dados mais recentes que 17/11/2025.

---

## 🛠️ Possíveis Problemas e Soluções

### **Problema 1: Workflow não aparece na lista**

**Possíveis causas:**
- Workflow está desabilitado
- Repositório tem Actions desabilitado
- Branch principal não é "main"

**Como resolver:**
1. Vá em: **Settings** → **Actions** → **General**
2. Verifique se está em: **"Allow all actions and reusable workflows"**
3. Em **Workflow permissions**: selecione **"Read and write permissions"**
4. Marque: ✅ **"Allow GitHub Actions to create and approve pull requests"**

### **Problema 2: Workflow executou mas não commitou**

**Possíveis causas:**
- Scraping falhou (erro 503, timeout, etc.)
- Nenhum dado novo encontrado
- Workflow tem `continue-on-error: true` (não falha mesmo com erro)

**Como verificar:**
```bash
# No terminal local:
git fetch origin main
git log origin/main -5 --format="%ai %s"

# Procure por commits recentes com "auto-update"
# Se não houver, o ETL falhou silenciosamente
```

**Como resolver:**
- Se for bloqueio (503): executar localmente
- Se for outro erro: corrigir o código conforme o log

### **Problema 3: Site não atualiza mesmo após commit**

**Possíveis causas:**
- GitHub Pages não fez deploy
- Cache do navegador
- Deploy falhou

**Como resolver:**

1. **Verificar se o deploy aconteceu:**
   - Vá em: **Settings** → **Pages**
   - Deve mostrar: ✅ "Your site is live at https://..."
   - Verifique a data do último deploy

2. **Limpar cache do navegador:**
   - Chrome/Edge: `Ctrl + Shift + R` (Windows) ou `Cmd + Shift + R` (Mac)
   - Firefox: `Ctrl + F5` (Windows) ou `Cmd + Shift + R` (Mac)
   - Safari: `Cmd + Option + R`

3. **Verificar o step de deploy nos logs:**
   ```
   ▶ Deploy to GitHub Pages
   ```
   Deve mostrar: ✅ "Deployment successful"

---

## 📝 Checklist de Diagnóstico

Execute este checklist para identificar o problema:

- [ ] **Step 1**: Acessei https://github.com/tadeugomes/balneabilidade/actions
- [ ] **Step 2**: Vi execuções recentes do workflow
- [ ] **Step 3**: Abri os logs da execução mais recente
- [ ] **Step 4**: Li os logs do step "Run ETL to refresh data"
- [ ] **Step 5**: Identifiquei o erro nos logs (503, timeout, outro)
- [ ] **Step 6**: Verifiquei se houve commit de "auto-update" no main
- [ ] **Step 7**: Verifiquei o step "Deploy to GitHub Pages"
- [ ] **Step 8**: Confirmei que o site está publicado em Settings → Pages

---

## 🎯 Próximos Passos

**Após verificar os logs:**

### Se for erro 503 (bloqueio):
➡️ Use a **execução local** (veja `PROXY_ISSUE.md`)

### Se for timeout:
➡️ Execute manualmente com timeout maior ou localmente

### Se for mudança no formato do PDF:
➡️ Avise para ajustarmos as regex de parsing

### Se os dados foram atualizados mas o site não mudou:
➡️ Limpe o cache do navegador e aguarde alguns minutos

---

## 📞 Informações Úteis

**URL do GitHub Actions:**
https://github.com/tadeugomes/balneabilidade/actions

**URL do site:**
https://tadeugomes.github.io/balneabilidade/

**Branch principal:**
`main`

**Workflow file:**
`.github/workflows/update_deploy.yml`

**Horário de execução automática:**
Quintas-feiras às 15:00 UTC (12:00 horário do Maranhão)

---

**Última atualização**: 09/02/2026
