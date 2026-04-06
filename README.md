# 🧠 SafeAge

### Utilizando Visão Computacional, NVR Open-Source e Containers Docker

---

## 📌 Sobre o Projeto

Este projeto tem como objetivo desenvolver um **sistema inteligente de monitoramento residencial** voltado para **idosos que moram sozinhos**, utilizando:

* 📹 Câmera IP
* 🧠 Visão computacional com IA
* 📦 Containers Docker
* 🖥️ Servidor Linux
* 🔔 Sistema configurável de notificações

O sistema permite detectar eventos como:

* Inatividade prolongada
* Movimento fora de horário padrão
* Permanência excessiva em área específica
* Entrada em áreas restritas
* Eventos anômalos configuráveis

---

## 🎓 Contexto Acadêmico

Projeto desenvolvido como **Trabalho de Conclusão de Curso (TCC)**
Curso: Tecnólogo em [NOME DO CURSO]

A proposta é fundamentada em:

> CAMARANO, Ana Amélia; KANSO, Solange; FERNANDES, Daniele. *Idoso, família e domicílio: uma revisão narrativa sobre a decisão de morar sozinho*. Revista Brasileira de Estudos de População, v. 40, 2023.

O estudo evidencia o crescimento de idosos que vivem sozinhos no Brasil, destacando desafios relacionados à segurança e suporte familiar — contexto que fundamenta a solução proposta.

---

## 🏗️ Arquitetura do Sistema

### 🔹 Componentes

* **Câmera IP Intelbras IM5 SC** (stream RTSP)
* **Frigate NVR (Open-Source)** – Processamento com IA
* **MQTT (Mosquitto)** – Comunicação de eventos
* **Backend (FastAPI)** – Regras configuráveis
* **PostgreSQL** – Persistência de dados
* **Frontend Web** – Painel administrativo
* **Sistema de Notificação** – Telegram + Email

---

## 🐳 Arquitetura em Containers

Todos os serviços são executados via Docker Compose:

```bash
docker compose up -d
```

### Serviços:

| Serviço  | Função                        |
| -------- | ----------------------------- |
| frigate  | Processamento de vídeo com IA |
| mqtt     | Broker de eventos             |
| postgres | Banco de dados                |
| backend  | API de regras                 |
| frontend | Interface administrativa      |

---

## ⚙️ Tecnologias Utilizadas

* Docker
* Docker Compose
* Frigate NVR
* FastAPI (Python)
* PostgreSQL
* Eclipse Mosquitto (MQTT)
* HTML/CSS/JS (Frontend)
* Linux Server
* RTSP / ONVIF

Todas as tecnologias utilizadas são **open-source**.

---

## 🎥 Integração com a Câmera

Exemplo de URL RTSP utilizada:

```
rtsp://usuario:senha@IP_DA_CAMERA:554/cam/realmonitor?channel=1&subtype=0
```

Compatível com a Intelbras IM5 SC.

---

## 🧠 Inteligência do Sistema

O diferencial do projeto está na **camada de regras configuráveis**, permitindo:

* Definição de horários críticos
* Tempo máximo de inatividade
* Áreas monitoradas
* Tipo de notificação por evento
* Histórico de eventos

---

## 📂 Estrutura do Projeto

```
monitoramento-idoso/
│
├── README.md
├── docker-compose.yml
├── backend/
├── frontend/
├── frigate/
├── media/
└── docs/
```

---

## 🚀 Como Executar

### 1️⃣ Pré-requisitos

* Linux Server
* Docker instalado
* Docker Compose instalado
* Câmera IP configurada na rede

### 2️⃣ Clonar o repositório

```bash
git clone https://github.com/seu-usuario/monitoramento-idoso.git
cd monitoramento-idoso
```

### 3️⃣ Subir os containers

```bash
docker compose up -d
```

### 4️⃣ Acessar serviços

* Frigate: http://localhost:5000
* Backend API: http://localhost:8000

---

## 🔒 Requisitos do Sistema

### Funcionais

* Detectar presença de pessoa via IA
* Monitorar inatividade prolongada
* Registrar eventos em banco
* Permitir configuração de regras
* Enviar notificações automáticas

### Não Funcionais

* Utilizar apenas tecnologias open-source
* Executar em ambiente Linux
* Ser totalmente containerizado
* Permitir fácil replicação do ambiente

---

## 📊 Público-Alvo

* Familiares de idosos que moram sozinhos
* Instituições de cuidado domiciliar
* Pesquisadores em IoT e monitoramento inteligente

---

## 📚 Documentação Completa

A documentação acadêmica completa do TCC está disponível em:

```
/docs/TCC_COMPLETO.md
```

---

## 📌 Licença

Projeto desenvolvido para fins acadêmicos.

---

## 👨‍💻 Autor

[Seu Nome]
[Tecnólogo em Análise e Desenvolvimento de Sistemas]
[Fametro]
[2026]

