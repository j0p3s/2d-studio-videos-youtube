# 2D Studio Android — 0.1

Aplicação Android independente do PC, com exportação **1920×1080, 24 fps, H.264/AAC**, narração Microsoft Neural em inglês e limite de **600 segundos de áudio real**. A pasta chama-se `Adnroid-App`, conforme solicitado.

## Instalar e usar

Android **15 ou superior**. Instalar o APK debug disponibilizado pelo build ou compilar com Android Studio. Permitir notificações para acompanhar o serviço de exportação.

1. Escolher Gemini, OpenAI ou Claude e indicar uma chave API e um ID de modelo disponível nessa conta. A app não inclui modelos nem credenciais.
2. Indicar a região e chave de um recurso **Microsoft Azure Speech**. A voz é `en-US-AndrewMultilingualNeural`, com texto em inglês. Esta integração oficial exige Azure; não utiliza a sessão Edge gratuita do programa Windows.
3. Introduzir tema e duração pretendida entre 1 e 10 minutos. Gerar e rever o JSON do guião e das cenas.
4. Exportar. O áudio de cada cena determina os tempos reais; as legendas acompanham a cena correspondente. Se a narração ultrapassar 10 minutos, a app interrompe e pede para encurtar o plano. A duração escolhida é um objetivo, não preenchimento artificial com silêncio.
5. O MP4 fica em `Movies/2D-Studio`. Abrir ou partilhar pelo seletor Android. Não há publicação automática.

As chaves ficam cifradas com AES-GCM e Android Keystore, sem backup. O campo de chave corresponde ao fornecedor atualmente selecionado; ao mudar de fornecedor, introduzir a chave e modelo correspondentes. Acesso API e limites de utilização são próprios de cada serviço; esta versão não reutiliza o login dos CLIs do Windows.

## Processamento

- Internet: geração de texto/plano e voz Microsoft; dados enviados diretamente ao fornecedor selecionado e à Microsoft.
- Telemóvel: desenho vetorial com Canvas reutilizando um bitmap, carregamento da textura por OpenGL ES/EGL, codificação preferencialmente por hardware MediaCodec, áudio AAC e montagem MediaMuxer.
- Um serviço `mediaProcessing` mantém a tarefa em primeiro plano, com progresso, cancelamento e wakelock limitado. Não guarda todos os fotogramas na memória. As cenas são geradas a partir de um esquema limitado; código arbitrário do modelo não é executado.
- Até 100 cenas, 36 palavras por cena e 1 500 palavras no plano. O limite final é calculado pelo tamanho PCM a 24 kHz/16 bits/mono.
- O codec escolhido aparece no progresso. Se não existir um encoder por hardware, tenta um encoder disponível por software. Falhas de configuração/render são apresentadas; não há garantia de desempenho em tempo real.

## Testar no RedMagic

Os botões **Device benchmark** exportam vídeos silenciosos de 10 segundos ou 10 minutos em 1080p, sem chaves API. São testes de render/codec, não testes da qualidade de voz ou IA. Depois testar um vídeo narrado com credenciais válidas. Verificar som, sincronização, duração, temperatura e comportamento em segundo plano.

Não foi possível executar no RedMagic nesta sessão: não havia dispositivo ADB ligado. A compilação não comprova que um render completo de 10 minutos funciona nesse aparelho. Não existem resultados de velocidade/temperatura do telefone.

## Compilar

JDK 17, Android SDK platform 35/build-tools 35.0.0. O Gradle Wrapper fixa Gradle 8.11.1 e AGP 8.9.1.

```sh
./gradlew testDebugUnitTest assembleDebug lintDebug
```

No Windows: `gradlew.bat`. Configurar `ANDROID_HOME` ou `local.properties` (não versionado). O workflow `Android APK` no GitHub executa os testes, lint e compilação e disponibiliza o APK como artifact. O APK debug é assinado para testes; não é uma publicação Play Store.

Validação local em 10/11/2026: `assembleDebug`, `testDebugUnitTest` (7 testes, zero falhas) e `lintDebug` concluídos com sucesso. O lint mantém avisos de internacionalização/SharedPreferences; não foram suprimidos erros. Isto não substitui testes de execução no telefone.

## Limites desta primeira versão

É um motor Android novo com quatro cenários e quatro adereços animados, personagem consistente, legendas por cena e planos editáveis. **Não é uma conversão integral do GrowKaz/Three.js:** ainda não tem a mesma variedade cinematográfica, música/SFX, editor de miniaturas, alinhamento palavra a palavra ou publicação YouTube da aplicação desktop. Não há retoma automática de um render interrompido; o plano fica guardado para nova tentativa. Os serviços API não foram testados com contas reais no Android nesta sessão. O esquema exige `language=en`, mas não deteta automaticamente português introduzido manualmente no JSON.

Referências: [MediaCodec](https://developer.android.com/reference/android/media/MediaCodec), [Microsoft Speech REST](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/rest-text-to-speech), [Gemini generateContent](https://ai.google.dev/api/generate-content), [OpenAI Chat Completions](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create).
