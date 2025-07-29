# Claude Code Provider Balancer - Architecture Diagrams

## System Architecture Overview

```mermaid
graph TB
    subgraph "Client Layer"
        C1[Claude Code CLI]
        C2[HTTP Client]
        C3[Third-party App]
    end
    
    subgraph "FastAPI Application Layer"
        LB[FastAPI Server<br/>Port 9090]
        MW[Middleware<br/>Logging & Error Handling]
        RV[Request Validation<br/>Pydantic Models]
    end
    
    subgraph "Request Processing Pipeline"
        DD[Deduplication Cache<br/>SHA-256 Signatures]
        FC[Format Conversion<br/>Anthropic ↔ OpenAI]
        TC[Token Counting<br/>tiktoken Integration]
    end
    
    subgraph "Provider Management Layer"
        PM[Provider Manager<br/>src/core/provider_manager/]
        PC[Configuration<br/>config.yaml]
        HM[Health Monitor<br/>Error Threshold & Cooldown]
        LBS[Load Balancing<br/>Priority/RoundRobin/Random]
        OH[OAuth Handler<br/>Token Management & Refresh]
    end
    
    subgraph "Provider Ecosystem"
        subgraph "Anthropic Providers"
            P1[Anthropic Official]
            P2[GAC Provider]
            P3[Custom Anthropic]
        end
        subgraph "OpenAI Providers"
            P4[OpenRouter]
            P5[Azure OpenAI]
            P6[Custom OpenAI]
        end
        subgraph "OAuth Providers"
            P7[Claude Code OAuth]
            P8[Other OAuth Providers]
        end
    end
    
    C1 --> LB
    C2 --> LB
    C3 --> LB
    
    LB --> MW
    MW --> RV
    RV --> DD
    DD --> FC
    FC --> TC
    TC --> PM
    
    PM --> PC
    PM --> HM
    PM --> LBS
    PM --> OH
    
    PM --> P1
    PM --> P2
    PM --> P3
    PM --> P4
    PM --> P5
    PM --> P6
    PM --> P7
    PM --> P8
    
    style LB fill:#e1f5fe
    style PM fill:#f3e5f5
    style DD fill:#fff3e0
    style FC fill:#e8f5e8
    style OH fill:#e1f5fe
    style P1 fill:#c8e6c9
    style P4 fill:#ffecb3
    style P7 fill:#fce4ec
```

## Detailed Request Processing Flow

```mermaid
sequenceDiagram
    participant Client
    participant FastAPI as FastAPI Server
    participant Middleware as Middleware Layer
    participant Dedup as Deduplication Cache
    participant Converter as Format Converter
    participant ProviderMgr as Provider Manager
    participant Provider1
    participant Provider2
    
    Client->>FastAPI: POST /v1/messages
    FastAPI->>Middleware: Request Processing
    Middleware->>Middleware: Log Request & Validate
    Middleware->>Dedup: Generate Request Signature
    
    alt Duplicate Request Found
        Dedup->>Dedup: Wait for Existing Request
        Dedup-->>Client: Return Cached Result
    else New Request
        Dedup->>Converter: Process New Request
        
        alt OpenAI Provider Selected
            Converter->>Converter: Convert Anthropic → OpenAI Format
        else Anthropic Provider Selected
            Converter->>Converter: Pass Through Format
        end
        
        Converter->>ProviderMgr: Get Provider for Model
        ProviderMgr->>ProviderMgr: Apply Model Routing Rules
        ProviderMgr->>ProviderMgr: Filter Healthy Providers
        ProviderMgr-->>Converter: Return Primary Provider
        
        Converter->>Provider1: Send Request (Primary)
        
        alt Provider1 Success
            Provider1-->>Converter: Response
            
            alt OpenAI Response
                Converter->>Converter: Convert OpenAI → Anthropic Format
            else Anthropic Response
                Converter->>Converter: Pass Through Response
            end
            
            Converter->>ProviderMgr: Mark Provider1 Success
            Converter-->>Client: Forward Response
            
        else Provider1 Failure
            Provider1-->>Converter: Error/Timeout
            Converter->>ProviderMgr: Classify Error & Mark Failure
            
            alt Retriable Error
                ProviderMgr-->>Converter: Return Fallback Provider
                Converter->>Provider2: Send Request (Fallback)
                
                alt Provider2 Success
                    Provider2-->>Converter: Response
                    Converter->>Converter: Format Conversion (if needed)
                    Converter->>ProviderMgr: Mark Provider2 Success
                    Converter-->>Client: Forward Response
                else All Providers Failed
                    Converter-->>Client: 503 Service Unavailable
                end
            else Non-Retriable Error
                Converter-->>Client: Forward Original Error
            end
        end
    end
    
    Middleware->>Middleware: Log Response & Cleanup
```

## Stream vs Non-Stream Processing

```mermaid
graph TD
    Start[Request Received] --> Parse[Parse Request Body]
    Parse --> Dup{Duplicate Check}
    Dup -->|Yes| Wait[Wait for Original]
    Dup -->|No| Stream{stream=true?}
    
    Stream -->|Yes| StreamFlow[Streaming Processing]
    Stream -->|No| NonStream[Non-Streaming Processing]
    
    subgraph "Streaming Processing"
        StreamFlow --> StreamDedup[Skip Deduplication<br/>Unique Stream ID]
        StreamDedup --> StreamProvider[Select Provider]
        StreamProvider --> StreamReq[Initiate Stream Request]
        StreamReq --> StreamMonitor[Real-time Stream Monitoring]
        StreamMonitor --> ClientDisconnect{Client Connected?}
        ClientDisconnect -->|Yes| StreamChunk[Process Stream Chunk]
        ClientDisconnect -->|No| StreamAbort[Abort Stream]
        StreamChunk --> FormatStream[Format Conversion<br/>OpenAI→Anthropic if needed]
        FormatStream --> StreamResponse[Send to Client]
        StreamResponse --> StreamMore{More Chunks?}
        StreamMore -->|Yes| StreamMonitor
        StreamMore -->|No| StreamComplete[Mark Stream Complete]
        StreamAbort --> StreamCleanup[Cleanup Stream Resources]
        StreamComplete --> StreamCleanup
    end
    
    subgraph "Non-Streaming Processing"
        NonStream --> NonStreamProvider[Select Provider]
        NonStreamProvider --> DirectReq[Send Direct Request]
        DirectReq --> DirectResp[Receive Complete Response]
        DirectResp --> FormatDirect[Format Conversion if needed]
        FormatDirect --> DirectSuccess[Mark Success & Send Response]
    end
    
    StreamCleanup --> FinalCleanup[Final Resource Cleanup]
    DirectSuccess --> FinalCleanup
    Wait --> FinalCleanup
    FinalCleanup --> ProviderUpdate[Update Provider Stats]
    ProviderUpdate --> End[Request Complete]
    
    style StreamFlow fill:#e3f2fd
    style NonStream fill:#f1f8e9
    style FinalCleanup fill:#fff3e0
    style StreamAbort fill:#ffcdd2
```

## Format Conversion Architecture

```mermaid
graph TD
    subgraph "Request Format Conversion"
        AnthropicReq[Anthropic Request<br/>from Client] --> ModelRoute[Model Route<br/>Lookup]
        ModelRoute --> ProviderType{Provider Type}
        
        ProviderType -->|anthropic| PassThrough[Pass Through<br/>No Conversion]
        ProviderType -->|openai| ConvertReq[Convert to OpenAI Format]
        ProviderType -->|zed| ZedConvert[Convert to Zed Format]
        
        ConvertReq --> MessageConv[Convert Messages<br/>role, content, tools]
        MessageConv --> ToolConv[Convert Tool Definitions<br/>function → tools]
        ToolConv --> SystemConv[Convert System Message<br/>system → messages[0]]
        SystemConv --> OpenAIReq[OpenAI Compatible Request]
    end
    
    subgraph "Response Format Conversion"
        OpenAIResp[OpenAI Response] --> RespType{Response Type}
        AnthropicResp[Anthropic Response] --> DirectResp[Direct Response<br/>to Client]
        ZedResp[Zed Response] --> ZedRespConv[Convert from Zed]
        
        RespType -->|streaming| StreamConv[Stream Conversion]
        RespType -->|non-streaming| DirectConv[Direct Conversion]
        
        StreamConv --> StreamChunkConv[Convert Each Chunk<br/>delta → content_block_delta]
        StreamChunkConv --> AnthropicStream[Anthropic Stream Format]
        
        DirectConv --> ContentConv[Convert Content<br/>choices → content]
        ContentConv --> UsageConv[Convert Usage<br/>usage → usage]
        UsageConv --> AnthropicResp2[Anthropic Response Format]
        
        ZedRespConv --> AnthropicResp3[Anthropic Response Format]
    end
    
    PassThrough --> DirectProvider[Direct to Provider]
    OpenAIReq --> OpenAIProvider[OpenAI Provider]
    ZedConvert --> ZedProvider[Zed Provider]
    
    DirectProvider --> AnthropicResp
    OpenAIProvider --> OpenAIResp
    ZedProvider --> ZedResp
    
    AnthropicStream --> Client[Client Response]
    AnthropicResp2 --> Client
    AnthropicResp3 --> Client
    DirectResp --> Client
    
    style ConvertReq fill:#fff3e0
    style StreamConv fill:#e3f2fd
    style PassThrough fill:#c8e6c9
    style Client fill:#e8f5e8
```

## Provider Selection and Failover

```mermaid
graph TD
    ModelReq[Client Model Request<br/>e.g., claude-3-5-sonnet] --> ModelMap[Model Route Mapping<br/>Wildcard Pattern Matching]
    ModelMap --> ProviderList[Get Provider Options<br/>Priority Sorted List]
    
    ProviderList --> HealthCheck[Health Check]
    HealthCheck --> Healthy{Provider<br/>Health Status}
    Healthy -->|Healthy| SelectionStrategy[Apply Selection Strategy]
    Healthy -->|Failed| Cooldown{In Cooldown<br/>Period?}
    
    Cooldown -->|Yes| Skip[Skip Provider]
    Cooldown -->|No| IdleRecovery[Attempt Idle Recovery]
    
    SelectionStrategy --> Strategy{Strategy Type}
    Strategy -->|priority| PrioritySelect[Select by Priority<br/>lowest number first]
    Strategy -->|round_robin| RoundRobinSelect[Round Robin Selection<br/>rotate through providers]
    Strategy -->|random| RandomSelect[Random Selection<br/>from healthy providers]
    
    PrioritySelect --> Attempt1[Attempt Primary Provider]
    RoundRobinSelect --> Attempt1
    RandomSelect --> Attempt1
    IdleRecovery --> Attempt1
    Skip --> NextProvider[Get Next Provider]
    
    Attempt1 --> Success1{Request<br/>Success?}
    Success1 -->|Yes| UpdateSuccess[Update Provider Stats<br/>Mark Success]
    Success1 -->|No| ErrorClassify[Classify Error Type]
    
    ErrorClassify --> ErrorType{Error Type}
    ErrorType -->|4xx Client Error| ClientError[Return Client Error<br/>No Failover]
    ErrorType -->|5xx Server Error| ServerError{Retryable?}
    ErrorType -->|Timeout| TimeoutError[Mark Timeout Failure]
    ErrorType -->|Network Error| NetworkError[Mark Network Failure]
    ErrorType -->|Overloaded| OverloadError[Mark Overload Failure]
    
    ServerError -->|Yes| MarkFailure[Mark Provider Failed<br/>Start Cooldown]
    ServerError -->|No| ClientError
    TimeoutError --> MarkFailure
    NetworkError --> MarkFailure
    OverloadError --> MarkFailure
    
    MarkFailure --> HasMore{More Providers<br/>Available?}
    HasMore -->|Yes| NextProvider
    HasMore -->|No| AllFailed[All Providers Exhausted]
    
    NextProvider --> Attempt2[Attempt Next Provider]
    Attempt2 --> Success2{Request<br/>Success?}
    Success2 -->|Yes| UpdateSuccess
    Success2 -->|No| ErrorClassify
    
    AllFailed --> Return503[Return 503<br/>Service Unavailable]
    
    UpdateSuccess --> ClientResponse[Send Response to Client]
    ClientError --> ClientResponse
    Return503 --> ClientResponse
    
    style UpdateSuccess fill:#c8e6c9
    style AllFailed fill:#ffcdd2
    style Return503 fill:#ffcdd2
    style ClientError fill:#ffecb3
    style MarkFailure fill:#fff3e0
```

## Request Deduplication Mechanism

```mermaid
graph LR
    subgraph "Request Processing"
        Req1[Request 1] --> Sig1[Generate Signature]
        Req2[Request 2<br/>Duplicate] --> Sig2[Generate Signature]
        Req3[Request 3<br/>Stream] --> Sig3[Unique Stream Signature]
    end
    
    subgraph "Deduplication Logic"
        Sig1 --> Check1{Signature in Cache?}
        Sig2 --> Check2{Signature in Cache?}
        Sig3 --> Process3[Process Directly<br/>No Deduplication]
    end
    
    Check1 -->|No| Store1[Store in Cache<br/>Create Future]
    Check1 -->|Yes| Wait1[Wait for Existing]
    
    Check2 -->|No| Store2[Store in Cache]
    Check2 -->|Yes| Wait2[Wait for Existing<br/>Request 1]
    
    Store1 --> Process1[Process Request 1]
    Process1 --> Complete1[Complete & Cleanup]
    
    Wait2 --> Complete1
    Complete1 --> Response[Send Response<br/>to Both Clients]
    
    Process3 --> Complete3[Complete Stream]
    
    style Store1 fill:#e8f5e8
    style Wait2 fill:#fff3e0
    style Process3 fill:#e3f2fd
```

## Error Handling and Classification

```mermaid
graph TD
    Error[Exception Caught] --> HTTP{HTTP Status Available?}
    
    HTTP -->|Yes| Status{Status Code}
    HTTP -->|No| Type[Exception Type Analysis]
    
    Status -->|4xx| Client[Client Error]
    Status -->|5xx| Server[Server Error]
    Status -->|Timeout| Timeout[Timeout Error]
    
    Type --> Network[Network Error]
    Type --> Parse[Parse Error]
    Type --> Stream[Stream Error]
    
    Client --> Retryable1{Retryable?}
    Server --> Retryable2{Retryable?}
    Timeout --> Failover1[Failover]
    Network --> Failover2[Failover]
    Parse --> NoFailover1[No Failover]
    Stream --> StreamCheck{Stream Error Type}
    
    StreamCheck -->|overloaded_error| Failover3[Failover]
    StreamCheck -->|Other| NoFailover2[No Failover]
    
    Retryable1 -->|No| NoFailover3[Return to Client]
    Retryable1 -->|Yes| Failover4[Failover]
    Retryable2 -->|No| NoFailover4[Return to Client]
    Retryable2 -->|Yes| Failover5[Failover]
    
    Failover1 --> NextProvider[Try Next Provider]
    Failover2 --> NextProvider
    Failover3 --> NextProvider
    Failover4 --> NextProvider
    Failover5 --> NextProvider
    
    NoFailover1 --> Client_Response[Return Error to Client]
    NoFailover2 --> Client_Response
    NoFailover3 --> Client_Response
    NoFailover4 --> Client_Response
    
    NextProvider --> Exhausted{Providers Exhausted?}
    Exhausted -->|No| AttemptNext[Attempt Next Provider]
    Exhausted -->|Yes| ServiceUnavailable[503 Service Unavailable]
    
    AttemptNext --> Success{Success?}
    Success -->|Yes| ClientSuccess[Return Success]
    Success -->|No| Error
    
    style Failover1 fill:#fff3e0
    style NoFailover1 fill:#ffcdd2
    style ClientSuccess fill:#c8e6c9
    style ServiceUnavailable fill:#ffcdd2
```

## Resource Cleanup Process

```mermaid
graph TD
    RequestComplete[Request Processing Complete] --> CleanupType{Cleanup Trigger}
    
    CleanupType -->|Success| SuccessCleanup[Success Cleanup]
    CleanupType -->|Error| ErrorCleanup[Error Cleanup]
    CleanupType -->|Timeout| TimeoutCleanup[Timeout Cleanup]
    CleanupType -->|Client Disconnect| DisconnectCleanup[Disconnect Cleanup]
    
    SuccessCleanup --> ProviderSuccess[Mark Provider Success]
    ErrorCleanup --> ProviderFailure[Mark Provider Failure]
    TimeoutCleanup --> ProviderFailure
    DisconnectCleanup --> PartialCleanup[Partial Cleanup]
    
    ProviderSuccess --> UpdateStats[Update Success Stats]
    ProviderFailure --> StartCooldown[Start Provider Cooldown]
    PartialCleanup --> LogDisconnect[Log Client Disconnect]
    
    UpdateStats --> DedupeCleanup[Cleanup Deduplication State]
    StartCooldown --> DedupeCleanup
    LogDisconnect --> DedupeCleanup
    
    DedupeCleanup --> RemoveSignature[Remove Request Signature]
    RemoveSignature --> CompleteFuture[Complete Pending Futures]
    CompleteFuture --> LogCompletion[Log Request Completion]
    
    LogCompletion --> FinalCleanup[Final Resource Cleanup]
    FinalCleanup --> Done[Cleanup Complete]
    
    style ProviderSuccess fill:#c8e6c9
    style ProviderFailure fill:#ffcdd2
    style Done fill:#e8f5e8
```

## Complete Data Flow Architecture

```mermaid
graph TB
    subgraph "Client Layer"
        CC[Claude Code CLI]
        HC[HTTP Clients]
        TA[Third-party Apps]
    end
    
    subgraph "Entry Point"
        FE[FastAPI Endpoints<br/>/v1/messages<br/>/v1/messages/count_tokens<br/>/providers]
    end
    
    subgraph "Request Processing Pipeline"
        MW[Middleware Layer<br/>- Logging<br/>- Error Handling<br/>- Client Disconnect Detection]
        RV[Request Validation<br/>- Pydantic Models<br/>- Schema Enforcement]
        DD[Deduplication System<br/>- SHA-256 Signatures<br/>- Concurrent Request Handling]
        TC[Token Counting<br/>- tiktoken Integration<br/>- Usage Estimation]
    end
    
    subgraph "Core Processing Engine"
        PM[Provider Manager<br/>- Health Monitoring<br/>- Load Balancing<br/>- Failover Logic]
        MR[Model Router<br/>- Wildcard Matching<br/>- Priority Selection<br/>- Provider Mapping]
        FC[Format Converter<br/>- Anthropic ↔ OpenAI<br/>- Stream Processing<br/>- Error Translation]
    end
    
    subgraph "Provider Ecosystem"
        subgraph "Anthropic Compatible"
            ANT[Anthropic Official]
            GAC[GAC Provider]
            CAN[Custom Anthropic]
        end
        
        subgraph "OpenAI Compatible"
            OPR[OpenRouter]
            AZO[Azure OpenAI]
            COA[Custom OpenAI]
        end
        
        subgraph "OAuth Compatible"
            CCO[Claude Code OAuth]
            OTH[Other OAuth Providers]
        end
    end
    
    subgraph "Configuration & State"
        CFG[config.yaml<br/>- Provider Settings<br/>- Model Routes<br/>- Global Config]
        HM[Health Monitor<br/>- Error Threshold & Counting<br/>- Cooldown Timers<br/>- Auto Recovery Logic]
        CACHE[Request Cache<br/>- SHA-256 Deduplication<br/>- Concurrent Response Sharing]
        LOGS[Logging System<br/>- Structured JSON Logs<br/>- LogEvent Enums<br/>- Error Classification]
        OAUTH[OAuth Manager<br/>- Token Storage & Refresh<br/>- Multi-user Support<br/>- Auto Refresh Loop]
    end
    
    CC --> FE
    HC --> FE
    TA --> FE
    
    FE --> MW
    MW --> RV
    RV --> DD
    DD --> TC
    TC --> PM
    
    PM --> MR
    MR --> FC
    
    PM -.-> CFG
    PM -.-> HM
    PM -.-> OAUTH
    DD -.-> CACHE
    MW -.-> LOGS
    
    FC --> ANT
    FC --> GAC
    FC --> CAN
    FC --> OPR
    FC --> AZO
    FC --> COA
    FC --> CCO
    FC --> OTH
    
    style FE fill:#e1f5fe
    style PM fill:#f3e5f5
    style FC fill:#e8f5e8
    style DD fill:#fff3e0
    style ANT fill:#c8e6c9
    style OPR fill:#ffecb3
    style CCO fill:#fce4ec
    style CFG fill:#f1f8e9
    style OAUTH fill:#e3f2fd
```

## Configuration Hot Reload Flow

```mermaid
sequenceDiagram
    participant Admin
    participant API as FastAPI /providers/reload
    participant PM as Provider Manager
    participant Config as config.yaml
    participant Providers as Active Providers
    
    Admin->>API: POST /providers/reload
    API->>Config: Read Updated Configuration
    Config-->>API: Return New Config Data
    
    API->>PM: Parse New Configuration
    PM->>PM: Validate Provider Settings
    PM->>PM: Validate Model Routes
    
    alt Configuration Valid
        PM->>Providers: Update Provider Pool
        PM->>PM: Preserve Health Status
        PM->>PM: Apply New Routes
        PM-->>API: Success Response
        API-->>Admin: 200 OK - Reloaded Successfully
        
    else Configuration Invalid
        PM-->>API: Validation Error
        API-->>Admin: 400 Bad Request - Invalid Config
    end
    
    Note over PM: Service continues running with previous config on error
```

## Health Check and Error Threshold System

```mermaid
graph TD
    Error[Provider Error Occurs] --> Classify[Classify Error Type]
    
    Classify --> ErrorType{Error Type}
    ErrorType -->|Unhealthy Error| Record[Record Error Count]
    ErrorType -->|Other Error| NoRecord[Skip Error Recording]
    
    Record --> Count[Current Error Count]
    Count --> Threshold{Count >= Threshold?}
    
    Threshold -->|Yes| MarkUnhealthy[Mark Provider Unhealthy]
    Threshold -->|No| BelowThreshold[Below Threshold]
    
    MarkUnhealthy --> StartCooldown[Start Cooldown Period]
    StartCooldown --> Failover[Trigger Failover]
    
    BelowThreshold --> LogBelow[Log: count=X/Y threshold]
    LogBelow --> ReturnError[Return Error to Client]
    
    NoRecord --> DirectReturn[Return Error Directly]
    
    subgraph "Error Types Triggering Unhealthy"
        ET1[connection_error]
        ET2[timeout_error] 
        ET3[ssl_error]
        ET4[internal_server_error]
        ET5[bad_gateway]
        ET6[service_unavailable]
        ET7[too_many_requests]
        ET8[rate_limit_exceeded]
        ET9[Insufficient credits]
        ET10[没有可用token]
        ET11[无可用模型]
    end
    
    subgraph "HTTP Status Codes Triggering Unhealthy"
        HC1[402, 404, 408, 429]
        HC2[500, 502, 503, 504]
        HC3[520-524 Cloudflare]
    end
    
    subgraph "Cooldown and Recovery"
        StartCooldown --> CooldownTimer[Cooldown Timer: 180s default]
        CooldownTimer --> TimeExpired{Timer Expired?}
        TimeExpired -->|No| StillCooling[Provider Still Cooling Down]
        TimeExpired -->|Yes| AttemptRecovery[Attempt Recovery]
        AttemptRecovery --> Success{Recovery Success?}
        Success -->|Yes| ResetCount[Reset Error Count]
        Success -->|No| ExtendCooldown[Extend Cooldown]
        ResetCount --> MarkHealthy[Mark Provider Healthy]
    end
    
    style MarkUnhealthy fill:#ffcdd2
    style BelowThreshold fill:#fff3e0
    style MarkHealthy fill:#c8e6c9
    style Failover fill:#ff8a65
    style ResetCount fill:#c8e6c9
```

## OAuth Flow Integration

```mermaid
sequenceDiagram
    participant Client
    participant Balancer as Provider Balancer
    participant OAuth as OAuth Manager
    participant Provider as Claude Code Provider
    participant Anthropic as Anthropic API
    
    Client->>Balancer: POST /v1/messages (OAuth provider)
    Balancer->>OAuth: Get Valid Token
    
    alt Valid Token Available
        OAuth-->>Balancer: Return Access Token
        Balancer->>Provider: Request with Bearer Token
        Provider->>Anthropic: Forward Request
        Anthropic-->>Provider: Response
        Provider-->>Balancer: Response
        Balancer-->>Client: Response
        
    else Token Expired
        OAuth->>OAuth: Auto Refresh Token
        
        alt Refresh Success
            OAuth-->>Balancer: Return New Token
            Balancer->>Provider: Request with New Token
            Provider->>Anthropic: Forward Request
            Anthropic-->>Provider: Response
            Provider-->>Balancer: Response
            Balancer-->>Client: Response
            
        else Refresh Failed
            OAuth-->>Balancer: Auth Error
            Balancer-->>Client: 401 Unauthorized
        end
        
    else No Valid Token
        OAuth-->>Balancer: No Auth Available
        Balancer-->>Client: 401 Unauthorized<br/>with OAuth URL
    end
    
    Note over OAuth: Background auto-refresh runs every 30 minutes
    Note over OAuth: Multi-user token management with keyring storage
```

These diagrams provide a comprehensive visual representation of the Claude Code Provider Balancer architecture, covering all major flows, decision points, and system interactions including the latest health check threshold system and OAuth integration.