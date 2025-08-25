# Instruções para Configuração do Ambiente Python

## Configuração do Ambiente Virtual e Instalação de Dependências

1. **Crie um ambiente virtual Python** (venv):  
   ```bash
   python -m venv venv
   ```

2. **Ative o ambiente virtual**:  
   - No Windows:  
     ```bash
     .\venv\Scripts\activate
     ```  
   - No Linux/MacOS:  
     ```bash
     source venv/bin/activate
     ```

3. **Instale as dependências do projeto** (arquivo `requirements.txt`):  
   ```bash
   pip install -r requirements.txt
   ```
---
## Comandos do Projeto

- **`python3 server.py`**  
  Inicia o servidor que vai receber a transmissão via RTMP, metadados via HTTP e disponibiliza o streaming ao vivo via DASH com os eventos recebidos.

- **`python3 client.py`**  
  Inicia a transmissão de um vídeo para o servidor

## Funcionamento do Projeto

Este sistema implementa um servidor que:

* Recebe um fluxo RTMP,
* Disponibiliza a live via HTTP usando DASH,
* Suporta injeção de metadados,
* Atualiza o manifesto DASH (`live-manifest.mpd`) com esses metadados.

---
# server.py

## Rotas Flask

### `serve_dash(filename)`

* **Rota:** `/live/app/<path:filename>`
* **Descrição:** Serve os arquivos gerados pelo FFmpeg (segmentos `.m4s`, `manifest.mpd`).
* **Parâmetros:**

  * `filename`: nome do arquivo solicitado.
* **Retorno:** Arquivo solicitado.

---

### `stream_alive()`

* **Rota:** `/stream_alive`
* **Descrição:** Indica se o processo do FFmpeg ainda está rodando.
* **Retorno:**

  ```json
  {"alive": true}
  ```

---

### `receive_metadata()`

* **Rota:** `/metadata` (POST)
* **Descrição:** Recebe metadados no formato JSON e armazena em memória.
* **Formato esperado:**

  ```json
  {
    "metadata": "mensagem",
    "time": 12345
  }
  ```
* **Retorno:**

  ```json
  {"status": "ok", "received": "mensagem"}
  ```

---

### `metadata_feed()`

* **Rota:** `/metadata_feed`
* **Descrição:** Retorna todos os metadados recebidos até o momento.
* **Retorno:**

  ```json
  [
    {"metadata": "msg1", "time": 123},
    {"metadata": "msg2", "time": 456}
  ]
  ```

---

### `watch_page()`

* **Rota:** `/watch`
* **Descrição:** Renderiza a página `live.html`, que deve conter o player de vídeo.

---

## Funções Utilitárias

### `clean(path)`

* **Descrição:** Remove todos os arquivos de um diretório, exceto `.gitkeep`.
* **Exceções:** Lança `NotADirectoryError` se o caminho não for um diretório.

---

### `run_ffmpeg(cmd, name)`

* **Descrição:** Executa um processo FFmpeg em uma thread separada.
* **Parâmetros:**

  * `cmd`: lista com o comando FFmpeg.
  * `name`: rótulo do processo (ex.: `"DASH"`).
* **Funcionamento:**

  1. Limpa o diretório `live/app`.
  2. Executa o FFmpeg via `subprocess.Popen`.
  3. Se for `"DASH"`, guarda em `ffmpeg_dash_proc`.
  4. Aguarda o término e imprime o código de saída.

---

### `wait_for_manifest()`

* **Descrição:** Aguarda até que o arquivo `manifest.mpd` seja criado e tenha tamanho válido.
* **Uso:** Garantir que o manifesto esteja pronto antes de clientes se conectarem.

---

## Manipulação do Manifesto MPEG-DASH

### `write_live_manifest(mpd_path, ns, persistent_events, live_mpd_path, metadata_index)`

* **Descrição:** Atualiza o `live-manifest.mpd` incluindo eventos (`EventStream`) com os metadados recebidos.
* **Parâmetros:**

  * `mpd_path`: caminho do manifesto original (`manifest.mpd`).
  * `ns`: namespace XML do MPEG-DASH.
  * `persistent_events`: lista de eventos já inseridos.
  * `live_mpd_path`: destino do manifesto atualizado.
  * `metadata_index`: índice do próximo metadado a inserir.
* **Funcionamento:**

  1. Carrega `manifest.mpd`.
  2. Localiza `<Period>`.
  3. Cria `<EventStream>` com eventos persistentes.
  4. Se houver novos metadados em `metadata_array`, adiciona como `<Event>`.
  5. Remove `EventStream` antigos e adiciona o novo.
  6. Salva o novo `manifest.mpd` com a `EventStream` em `live-manifest.mpd`.
* **Retorno:**

  * `True` → adicionou novo metadado.
  * `False` → nenhum metadado novo.

---

### `update_live_manifest()`

* **Descrição:** Loop que monitora continuamente o `manifest.mpd` e mantém atualizado o `live-manifest.mpd`.
* **Funcionamento:**

  * Inicializa lista de eventos (`persistent_events`) e contador (`metadata_index`).
  * A cada iteração:

    * Chama `write_live_manifest`.
    * Incrementa `metadata_index` se houve metadado novo.
    * Pausa por 200 ms.
  * Sai do loop se o FFmpeg encerrar.
  * Faz atualização final do manifesto.

---

## Execução Principal

### `if __name__ == "__main__":`

1. Cria o diretório `live/app` caso não exista.
2. Inicia as threads:

   * `run_ffmpeg(FFMPEG_DASH, "DASH")` → roda o FFmpeg.
   * `wait_for_manifest()` → espera pelo `manifest.mpd`.
   * `update_live_manifest()` → atualiza o manifesto com metadados.
3. Inicia o servidor Flask em `0.0.0.0:8080`.

---

# client.py

Este script implementa um cliente que:

* Envia um vídeo local via RTMP para o servidor (`rtmp://localhost:1935/live/app`),
* Envia metadados para o server.py,

---

## Funções

### `run_ffmpeg(cmd, name)`

* **Descrição:**
  Executa o processo do FFmpeg e inicia, em paralelo, o envio de metadados enquanto a transmissão ocorre.
* **Parâmetros:**

  * `cmd`: comando FFmpeg (lista).
  * `name`: nome identificador (ex.: `"Push"`).
* **Funcionamento:**

  1. Inicia o FFmpeg com `subprocess.Popen`.
  2. Cria uma thread para `send_metadata_loop(proc)` que envia metadados.
  3. Aguarda término da execução (`proc.wait()`).
  4. Exibe o código de saída.

---

### `send_metadata_loop(proc)`

* **Descrição:**
  Loop que envia mensagens JSON contendo metadados para o servidor enquanto o FFmpeg estiver em execução.
* **Parâmetros:**

  * `proc`: processo do FFmpeg (para checar se ainda está ativo).
* **Funcionamento:**

  1. Inicializa contador `counter = 1`.
  2. Enquanto o processo está ativo (`proc.poll() is None`) e contador < 100:

     * Monta mensagem no formato `"message N"`.
     * Envia via HTTP POST para `http://localhost:8080/metadata`.
     * Payload JSON:

       ```json
       {
         "metadata": "message N",
         "time": N
       }
       ```
     * Aguarda 0.5s antes do próximo envio.
  3. Incrementa contador a cada loop.

---

## Execução Principal

### `if __name__ == "__main__":`

* **Descrição:**
  Ponto de entrada do script.
* **Comportamento:**

  * Chama `run_ffmpeg(FFMPEG_PUSH, "Push")`.
  * Inicia transmissão do vídeo para RTMP.
  * Simultaneamente, inicia envio periódico de metadados para o servidor Flask.

---