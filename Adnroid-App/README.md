# 2D Studio Android — 0.2

Aplicação Android independente do PC, com exportação **1920×1080, 24 fps, H.264/AAC**, narração Microsoft Neural em inglês e limite de **600 segundos de áudio real**. A pasta chama-se `Adnroid-App`, conforme solicitado.

## Instalar e usar

Android **15 ou superior**. Instalar o APK debug disponibilizado pelo build ou compilar com Android Studio. Permitir notificações para acompanhar o serviço de exportação.

1. Escolher Gemini, OpenAI ou Claude e indicar uma chave API e um ID de modelo disponível nessa conta. A app não inclui modelos nem credenciais.
2. A voz **Microsoft Edge Neural gratuita** usa o pacote `edge-tts==7.3.1` no próprio telefone, através de Chaquopy/Python 3.12. Não exige conta, chave, região nem subscrição Azure. Voz: `en-US-AndrewMultilingualNeural`, em inglês. Requer internet e depende da disponibilidade do serviço Edge; não é um plano gratuito do Azure nem uma API com garantia de serviço. A geração de texto continua a exigir a chave do fornecedor de IA.
3. Introduzir tema e duração pretendida entre 1 e 10 minutos. Gerar e rever o JSON do guião e das cenas.
4. Exportar. O áudio de cada cena determina os tempos reais; as legendas acompanham a cena correspondente. Se a narração ultrapassar 10 minutos, a app interrompe e pede para encurtar o plano. A duração escolhida é um objetivo, não preenchimento artificial com silêncio.
5. O MP4 fica em `Movies/2D-Studio`. Abrir ou partilhar pelo seletor Android. Não há publicação automática.

As chaves de IA ficam cifradas com AES-GCM e Android Keystore, sem backup. O campo de chave corresponde ao fornecedor atualmente selecionado; ao mudar de fornecedor, introduzir a chave e modelo correspondentes. Acesso API e limites de utilização são próprios de cada serviço; esta versão não reutiliza o login dos CLIs do Windows.

## Processamento

- Internet: geração de texto/plano e voz Microsoft; dados enviados diretamente ao fornecedor selecionado e à Microsoft.
- Telemóvel: desenho vetorial com Canvas reutilizando um bitmap, carregamento da textura por OpenGL ES/EGL, codificação preferencialmente por hardware MediaCodec, áudio AAC e montagem MediaMuxer.
- Um serviço `mediaProcessing` mantém a tarefa em primeiro plano, com progresso, cancelamento e wakelock limitado. Não guarda todos os fotogramas na memória. As cenas são geradas a partir de um esquema limitado; código arbitrário do modelo não é executado.
- Até 100 cenas, 36 palavras por cena e 1 500 palavras no plano. O limite final é calculado pelo tamanho PCM a 24 kHz/16 bits/mono.
- O codec escolhido aparece no progresso. Se não existir um encoder por hardware, tenta um encoder disponível por software. Falhas de configuração/render são apresentadas; não há garantia de desempenho em tempo real.

## Testar no RedMagic

Os botões **Device benchmark** exportam vídeos silenciosos de 10 segundos ou 10 minutos em 1080p, sem chaves API. São testes de render/codec, não testes da qualidade de voz ou IA. Depois testar um vídeo narrado com credenciais válidas. Verificar som, sincronização, duração, temperatura e comportamento em segundo plano.

Na versão 0.2 foi ligado um RedMagic NX789J com Android 16. Passaram os testes instrumentados do menu, exportação ZIP, filtragem de tokens, voz Edge sem Azure e render narrado 1920×1080 H.264/AAC. Um crash Java controlado ficou persistido após reabrir. O MP4 curto foi descarregado e descodificado integralmente por FFmpeg sem erros. O benchmark prolongado é silencioso; não avalia uma narração completa de 10 minutos.

O benchmark silencioso de 10 minutos também passou no aparelho: encoder `c2.qti.avc.encoder`, 1920×1080, 24 fps, 14 400 fotogramas e 600,000 segundos de vídeo. O AAC inclui cerca de 0,107 segundos de padding. O MP4 foi descarregado e descodificado integralmente sem erros. O teste revelou e permitiu corrigir a espera repetida por EOS no áudio; o render passou após antecipar o escoamento do encoder e reutilizar a textura EGL em vez de a realocar a cada frame. Estes resultados não validam chamadas a fornecedores de guiões nem uma narração real de 10 minutos.

## Compilar

JDK 17, Android SDK platform 35/build-tools 35.0.0. O Gradle Wrapper fixa Gradle 8.11.1 e AGP 8.9.1.

```sh
./gradlew testDebugUnitTest assembleDebug lintDebug
```

No Windows: `gradlew.bat`. Configurar `ANDROID_HOME` ou `local.properties` (não versionado). O workflow `Android APK` no GitHub executa os testes, lint e compilação e disponibiliza o APK como artifact. O APK ARM64 inclui Python 3.12 e aiohttp 3.10.10; requer Python 3.12 também para compilar. Não suporta emuladores x86. O APK debug é assinado para testes; não é uma publicação Play Store.

Validação local em 10/11/2026: `assembleDebug`, `testDebugUnitTest` (7 testes, zero falhas) e `lintDebug` concluídos com sucesso. O lint mantém avisos de internacionalização/SharedPreferences; não foram suprimidos erros. Isto não substitui testes de execução no telefone.

## Limites desta primeira versão

É um motor Android novo com quatro cenários e quatro adereços animados, personagem consistente, legendas por cena e planos editáveis. **Não é uma conversão integral do GrowKaz/Three.js:** ainda não tem a mesma variedade cinematográfica, música/SFX, editor de miniaturas, alinhamento palavra a palavra ou publicação YouTube da aplicação desktop. Não há retoma automática de um render interrompido; o plano fica guardado para nova tentativa. A voz Edge foi testada no aparelho; as APIs de geração de guiões ainda não foram testadas com contas reais no Android. O esquema exige `language=en`, mas não deteta automaticamente português introduzido manualmente no JSON.

Referências: [MediaCodec](https://developer.android.com/reference/android/media/MediaCodec), [edge-tts](https://github.com/rany2/edge-tts), [Gemini generateContent](https://ai.google.dev/api/generate-content), [OpenAI Chat Completions](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create).

## Options → Debug / Diagnostics

- Ver registos recentes e exportar um ZIP pelo seletor Android: logs rotativos da app (cerca de 1 MB + anterior), último crash Java, motivos de saída do processo/ANRs, logcat do processo e dados de modelo/Android/codecs.
- Testar a voz gratuita, renders silenciosos de 10 segundos ou 10 minutos, registar um erro simulado e provocar um crash controlado com confirmação.
- Crashes persistem depois de reabrir. Não é enviado nada automaticamente. O FileProvider concede leitura ao destinatário escolhido.
- Chaves conhecidas e tokens Bearer são filtrados na exportação. Planos, narração e ficheiros áudio não são incluídos intencionalmente. Rever o relatório antes de partilhar.
- Licenças e atribuição do edge-tts (LGPLv3, com componente MIT) estão no APK e em `app/src/main/assets/licenses`. O pacote upstream é incluído sem modificações; o adaptador está em `src/main/python/edge_voice.py`.

Testes no dispositivo (compilar primeiro `assembleDebugAndroidTest` e instalar ambos os APKs):

```sh
adb shell am instrument -w com.j0p3s.studio.test/com.j0p3s.studio.DeviceChecks
adb shell am instrument -w -e skipUi true -e longRender true com.j0p3s.studio.test/com.j0p3s.studio.DeviceChecks
```

O primeiro exige o ecrã desbloqueado. O segundo executa um benchmark silencioso de 600 segundos. O argumento `-e crash true` provoca deliberadamente um crash para verificar o registo; não executar durante trabalhos importantes.
