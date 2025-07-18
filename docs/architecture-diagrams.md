# Request Processing Architecture Diagram

## System Architecture Overview

```mermaid
graph TB
    subgraph "Client Layer"
        C1[Claude Code CLI]
        C2[HTTP Client]
        C3[Third-party App]
    end
    
    subgraph "Load Balancer Layer"
        LB[FastAPI Application<br/>Port 8080]
    end
    
    subgraph "Provider Management"
        PM[Provider Manager]
        PC[Provider Config<br/>providers.yaml]
        HM[Health Monitor]
    end
    
    subgraph "Provider Pool"
        P1[Anthropic API<br/>Provider 1]
        P2[OpenAI Compatible<br/>Provider 2]
        P3[Zed Provider<br/>Provider 3]
        PN[Provider N<br/>...]
    end
    
    C1 --> LB
    C2 --> LB
    C3 --> LB
    
    LB --> PM
    PM --> PC
    PM --> HM
    
    PM --> P1
    PM --> P2
    PM --> P3
    PM --> PN
    
    style LB fill:#e1f5fe
    style PM fill:#f3e5f5
    style P1 fill:#e8f5e8
    style P2 fill:#fff3e0
    style P3 fill:#fce4ec
```

## Detailed Request Processing Flow

```mermaid
sequenceDiagram
    participant Client
    participant LoadBalancer as Load Balancer
    participant ProviderMgr as Provider Manager
    participant Provider1
    participant Provider2
    
    Client->>LoadBalancer: POST /v1/messages
    LoadBalancer->>LoadBalancer: Generate Request ID
    LoadBalancer->>LoadBalancer: Parse & Validate Request
    LoadBalancer->>LoadBalancer: Check for Duplicates
    
    alt Duplicate Request Found
        LoadBalancer->>LoadBalancer: Wait for Original Request
        LoadBalancer-->>Client: Return Cached Result
    else New Request
        LoadBalancer->>ProviderMgr: Get Provider Options
        ProviderMgr->>ProviderMgr: Filter Healthy Providers
        ProviderMgr-->>LoadBalancer: Return Provider List
        
        LoadBalancer->>Provider1: Send Request (Primary)
        
        alt Provider1 Success
            Provider1-->>LoadBalancer: Response
            LoadBalancer->>ProviderMgr: Mark Provider1 Success
            LoadBalancer-->>Client: Forward Response
        else Provider1 Failure
            Provider1-->>LoadBalancer: Error/Timeout
            LoadBalancer->>ProviderMgr: Mark Provider1 Failure
            LoadBalancer->>Provider2: Send Request (Fallback)
            
            alt Provider2 Success
                Provider2-->>LoadBalancer: Response
                LoadBalancer->>ProviderMgr: Mark Provider2 Success
                LoadBalancer-->>Client: Forward Response
            else All Providers Failed
                LoadBalancer-->>Client: 503 Service Unavailable
            end
        end
    end
    
    LoadBalancer->>LoadBalancer: Cleanup Request State
```

## Stream vs Non-Stream Processing

```mermaid
graph TD
    Start[Request Received] --> Parse[Parse Request Body]
    Parse --> Dup{Duplicate?}
    Dup -->|Yes| Wait[Wait for Original]
    Dup -->|No| Stream{Stream Request?}
    
    Stream -->|Yes| StreamFlow[Streaming Flow]
    Stream -->|No| NonStream[Non-Streaming Flow]
    
    subgraph "Streaming Processing"
        StreamFlow --> PreCheck[Pre-read Validation]
        PreCheck --> StreamGen[Stream Generation]
        StreamGen --> StreamMonitor[Real-time Monitoring]
        StreamMonitor --> StreamSuccess[Mark Success on Completion]
    end
    
    subgraph "Non-Streaming Processing"
        NonStream --> DirectReq[Direct Request]
        DirectReq --> DirectResp[Process Response]
        DirectResp --> DirectSuccess[Mark Success Immediately]
    end
    
    StreamSuccess --> Cleanup[Cleanup & Response]
    DirectSuccess --> Cleanup
    Wait --> Cleanup
    Cleanup --> End[Request Complete]
    
    style StreamFlow fill:#e3f2fd
    style NonStream fill:#f1f8e9
    style Cleanup fill:#fff3e0
```

## Provider Selection and Failover

```mermaid
graph TD
    ModelReq[Client Model Request] --> ModelMap[Model Route Mapping]
    ModelMap --> ProviderList[Get Provider Options]
    
    ProviderList --> Health{Check Provider Health}
    Health -->|Healthy| Priority[Apply Priority/Strategy]
    Health -->|Unhealthy| Skip[Skip Provider]
    
    Priority --> Attempt1[Attempt Provider 1]
    Skip --> Priority
    
    Attempt1 --> Success1{Success?}
    Success1 -->|Yes| MarkSuccess[Mark Provider Success]
    Success1 -->|No| ClassifyError[Classify Error Type]
    
    ClassifyError --> Retryable{Retryable Error?}
    Retryable -->|Yes| MarkFail1[Mark Provider Failed]
    Retryable -->|No| ReturnError[Return Error to Client]
    
    MarkFail1 --> HasMore{More Providers?}
    HasMore -->|Yes| Attempt2[Attempt Provider 2]
    HasMore -->|No| AllFailed[All Providers Failed]
    
    Attempt2 --> Success2{Success?}
    Success2 -->|Yes| MarkSuccess
    Success2 -->|No| MarkFail2[Mark Provider Failed]
    
    MarkFail2 --> AllFailed
    AllFailed --> Return503[Return 503 Error]
    
    MarkSuccess --> ClientResponse[Send Response to Client]
    ReturnError --> ClientResponse
    Return503 --> ClientResponse
    
    style MarkSuccess fill:#c8e6c9
    style AllFailed fill:#ffcdd2
    style Return503 fill:#ffcdd2
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

These diagrams provide a comprehensive visual representation of the request processing architecture, covering all major flows and decision points in the system.