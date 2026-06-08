import {
  AgentCoreApplication,
  AgentCoreMcp,
  type AgentCoreProjectSpec,
  type AgentCoreMcpSpec,
} from '@aws/agentcore-cdk';
import {
  CfnOutput,
  Fn,
  RemovalPolicy,
  Stack,
  type StackProps,
  aws_bedrock as bedrock,
  aws_iam as iam,
  aws_opensearchserverless as oss,
  aws_s3 as s3,
} from 'aws-cdk-lib';
import { Construct } from 'constructs';

export interface HarnessConfig {
  name: string;
  executionRoleArn?: string;
  memoryName?: string;
  containerUri?: string;
  hasDockerfile?: boolean;
  dockerfile?: string;
  codeLocation?: string;
  tools?: { type: string; name: string }[];
  apiKeyArn?: string;
}

export interface AgentCoreStackProps extends StackProps {
  /**
   * The AgentCore project specification containing agents, memories, and credentials.
   */
  spec: AgentCoreProjectSpec;
  /**
   * The MCP specification containing gateways and servers.
   */
  mcpSpec?: AgentCoreMcpSpec;
  /**
   * Credential provider ARNs from deployed state, keyed by credential name.
   */
  credentials?: Record<string, { credentialProviderArn: string; clientSecretArn?: string }>;
  /**
   * Harness role configurations.
   */
  harnesses?: HarnessConfig[];
}

/**
 * CDK Stack that deploys AgentCore infrastructure.
 *
 * This is a thin wrapper that instantiates L3 constructs.
 * All resource logic and outputs are contained within the L3 constructs.
 */
export class AgentCoreStack extends Stack {
  /** The AgentCore application containing all agent environments */
  public readonly application: AgentCoreApplication;

  constructor(scope: Construct, id: string, props: AgentCoreStackProps) {
    super(scope, id, props);

    const { spec, mcpSpec, credentials, harnesses } = props;

    // Create AgentCoreApplication with all agents and harness roles
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const appProps: Record<string, unknown> = { spec };
    if (harnesses?.length) {
      appProps.harnesses = harnesses;
    }
    this.application = new AgentCoreApplication(this, 'Application', appProps as any);

    // Create AgentCoreMcp if there are gateways configured
    if (mcpSpec?.agentCoreGateways && mcpSpec.agentCoreGateways.length > 0) {
      new AgentCoreMcp(this, 'Mcp', {
        projectName: spec.name,
        mcpSpec,
        agentCoreApplication: this.application,
        credentials,
        projectTags: spec.tags,
      });
    }

    // ── Knowledge Base: S3 data source bucket ──────────────────────────────
    const dataBucket = new s3.Bucket(this, 'KbDataBucket', {
      versioned: true,
      encryption: s3.BucketEncryption.S3_MANAGED,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      removalPolicy: RemovalPolicy.RETAIN,
      autoDeleteObjects: false,
    });

    // ── Knowledge Base: OpenSearch Serverless collection ───────────────────
    const ossEncPolicy = new oss.CfnSecurityPolicy(this, 'KbOssEncPolicy', {
      name: 'bartt-kb-enc',
      type: 'encryption',
      policy: JSON.stringify({
        Rules: [{ ResourceType: 'collection', Resource: ['collection/bartt-kb-vectors'] }],
        AWSOwnedKey: true,
      }),
    });

    const ossNetPolicy = new oss.CfnSecurityPolicy(this, 'KbOssNetPolicy', {
      name: 'bartt-kb-net',
      type: 'network',
      policy: JSON.stringify([{
        Rules: [
          { ResourceType: 'collection', Resource: ['collection/bartt-kb-vectors'] },
          { ResourceType: 'dashboard', Resource: ['collection/bartt-kb-vectors'] },
        ],
        AllowFromPublic: true,
      }]),
    });

    const ossCollection = new oss.CfnCollection(this, 'KbOssCollection', {
      name: 'bartt-kb-vectors',
      type: 'VECTORSEARCH',
    });
    ossCollection.addDependency(ossEncPolicy);
    ossCollection.addDependency(ossNetPolicy);

    // ── Knowledge Base: IAM role for Bedrock ───────────────────────────────
    const kbRole = new iam.Role(this, 'KbRole', {
      assumedBy: new iam.ServicePrincipal('bedrock.amazonaws.com', {
        conditions: {
          StringEquals: { 'aws:SourceAccount': this.account },
        },
      }),
    });
    kbRole.addToPolicy(new iam.PolicyStatement({
      actions: ['bedrock:InvokeModel'],
      resources: [
        `arn:aws:bedrock:${this.region}::foundation-model/amazon.titan-embed-text-v2:0`,
      ],
    }));
    kbRole.addToPolicy(new iam.PolicyStatement({
      actions: ['aoss:APIAccessAll'],
      resources: [ossCollection.attrArn],
    }));
    dataBucket.grantRead(kbRole);

    // ── Knowledge Base: OSS data access policy ────────────────────────────
    // Fn.sub is used so CDK token ARNs resolve correctly inside the JSON string.
    const ossAccessPolicy = new oss.CfnAccessPolicy(this, 'KbOssAccessPolicy', {
      name: 'bartt-kb-access',
      type: 'data',
      policy: Fn.sub(
        '[{"Rules":['
          + '{"ResourceType":"index","Resource":["index/bartt-kb-vectors/*"],'
          + '"Permission":["aoss:ReadDocument","aoss:WriteDocument",'
          + '"aoss:CreateIndex","aoss:DeleteIndex","aoss:UpdateIndex","aoss:DescribeIndex"]},'
          + '{"ResourceType":"collection","Resource":["collection/bartt-kb-vectors"],'
          + '"Permission":["aoss:CreateCollectionItems","aoss:DeleteCollectionItems",'
          + '"aoss:UpdateCollectionItems","aoss:DescribeCollectionItems"]}],'
          + '"Principal":["${KbRoleArn}",'
          + '"arn:aws:iam::${AWS::AccountId}:role/cdk-hnb659fds-cfn-exec-role-${AWS::AccountId}-${AWS::Region}"'
          + ']}]',
        { KbRoleArn: kbRole.roleArn },
      ),
    });

    // ── Knowledge Base: Create OSS vector index (native CFN resource) ──────
    const ossVectorIndex = new oss.CfnIndex(this, 'OssVectorIndex', {
      collectionEndpoint: ossCollection.attrCollectionEndpoint,
      indexName: 'bartt-kb-index',
      settings: {
        index: { knn: true },
      },
      mappings: {
        properties: {
          embedding: {
            type: 'knn_vector',
            dimension: 1024,
            method: { engine: 'faiss', name: 'hnsw', spaceType: 'l2' },
          },
          text: { type: 'text' },
          metadata: { type: 'text' },
        },
      },
    });
    ossVectorIndex.node.addDependency(ossAccessPolicy);
    ossVectorIndex.node.addDependency(ossCollection);

    // ── Knowledge Base: Bedrock Knowledge Base ────────────────────────────
    const kb = new bedrock.CfnKnowledgeBase(this, 'BartKnowledgeBase', {
      name: 'bartt-knowledge-base',
      roleArn: kbRole.roleArn,
      knowledgeBaseConfiguration: {
        type: 'VECTOR',
        vectorKnowledgeBaseConfiguration: {
          embeddingModelArn: `arn:aws:bedrock:${this.region}::foundation-model/amazon.titan-embed-text-v2:0`,
        },
      },
      storageConfiguration: {
        type: 'OPENSEARCH_SERVERLESS',
        opensearchServerlessConfiguration: {
          collectionArn: ossCollection.attrArn,
          vectorIndexName: 'bartt-kb-index',
          fieldMapping: {
            vectorField: 'embedding',
            textField: 'text',
            metadataField: 'metadata',
          },
        },
      },
    });
    kb.node.addDependency(ossVectorIndex);

    // ── Knowledge Base: S3 data source ────────────────────────────────────
    const kbDataSource = new bedrock.CfnDataSource(this, 'BartKbDataSource', {
      name: 'bartt-s3-data-source',
      knowledgeBaseId: kb.ref,
      dataSourceConfiguration: {
        type: 'S3',
        s3Configuration: {
          bucketArn: dataBucket.bucketArn,
        },
      },
      vectorIngestionConfiguration: {
        chunkingConfiguration: {
          chunkingStrategy: 'FIXED_SIZE',
          fixedSizeChunkingConfiguration: {
            maxTokens: 512,
            overlapPercentage: 20,
          },
        },
      },
    });

    // ── Knowledge Base: Grant agent execution role Retrieve permission ─────
    const agentEnv = this.application.environments.get('barttagent');
    if (agentEnv) {
      agentEnv.runtime.role.addToPrincipalPolicy(new iam.PolicyStatement({
        actions: ['bedrock:Retrieve', 'bedrock:RetrieveAndGenerate'],
        resources: [kb.attrKnowledgeBaseArn],
      }));
    }

    // Stack-level output
    new CfnOutput(this, 'StackNameOutput', {
      description: 'Name of the CloudFormation Stack',
      value: this.stackName,
    });

    // ── Knowledge Base: Outputs ────────────────────────────────────────────
    new CfnOutput(this, 'KnowledgeBaseId', {
      description: 'Bedrock Knowledge Base ID — set as KNOWLEDGE_BASE_ID env var',
      value: kb.ref,
    });
    new CfnOutput(this, 'KnowledgeBaseDataBucketName', {
      description: 'S3 bucket for Knowledge Base data source',
      value: dataBucket.bucketName,
    });
    new CfnOutput(this, 'KnowledgeBaseDataSourceId', {
      description: 'Data source ID for triggering ingestion jobs',
      value: kbDataSource.attrDataSourceId,
    });
  }
}
