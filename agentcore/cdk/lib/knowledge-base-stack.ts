import {
  CfnOutput,
  RemovalPolicy,
  Stack,
  type StackProps,
} from 'aws-cdk-lib';
import * as bedrock from 'aws-cdk-lib/aws-bedrock';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as aoss from 'aws-cdk-lib/aws-opensearchserverless';
import * as s3 from 'aws-cdk-lib/aws-s3';
import { Construct } from 'constructs';

export interface KnowledgeBaseStackProps extends StackProps {
  /** Short, slugified project name used for resource naming. */
  readonly projectName: string;
  /**
   * ARN of the IAM principal (user or role) that will create the
   * OpenSearch Serverless vector index post-deployment.
   * Defaults to the AWS account root principal.
   * @default `arn:aws:iam::{account}:root`
   */
  readonly adminPrincipalArn?: string;
}

/**
 * Creates all AWS infrastructure required for the BARTT Bedrock Knowledge Base:
 *
 *   S3 Bucket (document store)
 *   OpenSearch Serverless collection (vector store)
 *   Bedrock Knowledge Base
 *   Bedrock Data Source (S3 → KB)
 *   IAM role for Bedrock service principal
 *
 * **Post-deployment steps (cannot be automated via CloudFormation):**
 * 1. Create the vector index in OpenSearch Serverless (see README).
 * 2. Upload BARTT documents to the S3 bucket.
 * 3. Start a KB ingestion job to index the documents.
 */
export class KnowledgeBaseStack extends Stack {
  /** Bedrock Knowledge Base ID — set as KNOWLEDGE_BASE_ID env var on the agent. */
  public readonly knowledgeBaseId: string;
  /** Data Source ID — used to trigger KB sync jobs. */
  public readonly dataSourceId: string;
  /** S3 bucket name for BARTT source documents. */
  public readonly s3BucketName: string;

  constructor(scope: Construct, id: string, props: KnowledgeBaseStackProps) {
    super(scope, id, props);

    const { projectName, adminPrincipalArn } = props;
    // Normalise to lowercase-hyphen for resource names (AWS naming constraints).
    const slug = projectName.replace(/_/g, '-').toLowerCase();

    // Suffix avoids collisions when deploying the same project to multiple accounts/regions.
    const nameSuffix = `${this.account}-${this.region}`;

    const collectionName = `${slug}-kb`;
    const vectorIndexName = 'bartt-kb-index';
    const embeddingModelArn = `arn:aws:bedrock:${this.region}::foundation-model/amazon.titan-embed-text-v2:0`;

    // ------------------------------------------------------------------
    // 1. S3 Bucket for BARTT source documents
    // ------------------------------------------------------------------
    const dataBucket = new s3.Bucket(this, 'DataBucket', {
      bucketName: `${slug}-kb-data-${nameSuffix}`,
      versioned: true,
      encryption: s3.BucketEncryption.S3_MANAGED,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      enforceSSL: true,
      // RETAIN on stack deletion to prevent accidental data loss.
      removalPolicy: RemovalPolicy.RETAIN,
      autoDeleteObjects: false,
    });

    // ------------------------------------------------------------------
    // 2. IAM Role for the Bedrock Knowledge Base service principal
    // ------------------------------------------------------------------
    const kbRole = new iam.Role(this, 'KnowledgeBaseRole', {
      roleName: `${slug}-bedrock-kb-role-${this.region}`,
      assumedBy: new iam.ServicePrincipal('bedrock.amazonaws.com', {
        conditions: {
          StringEquals: { 'aws:SourceAccount': this.account },
        },
      }),
      description: 'Allows the Bedrock Knowledge Base to read S3 and access OpenSearch Serverless',
    });

    // Allow read access to the S3 data bucket.
    dataBucket.grantRead(kbRole);

    // Allow calling the embedding model for chunk vectorisation.
    kbRole.addToPolicy(
      new iam.PolicyStatement({
        sid: 'BedrockEmbeddingAccess',
        effect: iam.Effect.ALLOW,
        actions: ['bedrock:InvokeModel'],
        resources: [embeddingModelArn],
      }),
    );

    // Allow OpenSearch Serverless API access (index read/write).
    kbRole.addToPolicy(
      new iam.PolicyStatement({
        sid: 'AossApiAccess',
        effect: iam.Effect.ALLOW,
        actions: ['aoss:APIAccessAll'],
        resources: [`arn:aws:aoss:${this.region}:${this.account}:collection/*`],
      }),
    );

    // ------------------------------------------------------------------
    // 3. OpenSearch Serverless — Encryption security policy
    //    (must exist before the collection is created)
    // ------------------------------------------------------------------
    const encryptionPolicy = new aoss.CfnSecurityPolicy(this, 'AossEncryptionPolicy', {
      name: `${slug}-kb-enc`,
      type: 'encryption',
      policy: JSON.stringify([
        {
          Rules: [
            {
              ResourceType: 'collection',
              Resource: [`collection/${collectionName}`],
            },
          ],
          AWSOwnedKey: true,
        },
      ]),
    });

    // ------------------------------------------------------------------
    // 4. OpenSearch Serverless — Network policy
    //    AllowFromPublic is required so Bedrock can reach the collection.
    // ------------------------------------------------------------------
    const networkPolicy = new aoss.CfnSecurityPolicy(this, 'AossNetworkPolicy', {
      name: `${slug}-kb-net`,
      type: 'network',
      policy: JSON.stringify([
        {
          Rules: [
            { ResourceType: 'collection', Resource: [`collection/${collectionName}`] },
            { ResourceType: 'dashboard', Resource: [`collection/${collectionName}`] },
          ],
          AllowFromPublic: true,
        },
      ]),
    });

    // ------------------------------------------------------------------
    // 5. OpenSearch Serverless Collection (VECTORSEARCH type)
    // ------------------------------------------------------------------
    const aossCollection = new aoss.CfnCollection(this, 'AossCollection', {
      name: collectionName,
      type: 'VECTORSEARCH',
      description: `Vector search collection for ${projectName} BARTT Knowledge Base`,
    });
    // Policies must be created before the collection.
    aossCollection.addDependency(encryptionPolicy);
    aossCollection.addDependency(networkPolicy);

    // ------------------------------------------------------------------
    // 6. OpenSearch Serverless — Data access policy
    //    Grants the KB IAM role (and optional admin principal) read/write
    //    access to the collection and its indexes.
    // ------------------------------------------------------------------
    const principals: string[] = [kbRole.roleArn];
    if (adminPrincipalArn) {
      principals.push(adminPrincipalArn);
    } else {
      // Default: allow account root to manage the collection (useful for
      // manually creating the vector index post-deployment).
      principals.push(`arn:aws:iam::${this.account}:root`);
    }

    const accessPolicy = new aoss.CfnAccessPolicy(this, 'AossAccessPolicy', {
      name: `${slug}-kb-access`,
      type: 'data',
      policy: JSON.stringify([
        {
          Rules: [
            {
              ResourceType: 'collection',
              Resource: [`collection/${collectionName}`],
              Permission: [
                'aoss:CreateCollectionItems',
                'aoss:DeleteCollectionItems',
                'aoss:UpdateCollectionItems',
                'aoss:DescribeCollectionItems',
              ],
            },
            {
              ResourceType: 'index',
              Resource: [`index/${collectionName}/*`],
              Permission: [
                'aoss:CreateIndex',
                'aoss:DeleteIndex',
                'aoss:UpdateIndex',
                'aoss:DescribeIndex',
                'aoss:ReadDocument',
                'aoss:WriteDocument',
              ],
            },
          ],
          Principal: principals,
        },
      ]),
    });
    // Access policy depends on the collection existing first.
    accessPolicy.addDependency(aossCollection);

    // ------------------------------------------------------------------
    // 7. Bedrock Knowledge Base
    // ------------------------------------------------------------------
    const knowledgeBase = new bedrock.CfnKnowledgeBase(this, 'KnowledgeBase', {
      name: `${slug}-knowledge-base`,
      roleArn: kbRole.roleArn,
      description: 'BARTT Knowledge Base — grounded answers from BARTT business documents',
      knowledgeBaseConfiguration: {
        type: 'VECTOR',
        vectorKnowledgeBaseConfiguration: {
          embeddingModelArn,
        },
      },
      storageConfiguration: {
        type: 'OPENSEARCH_SERVERLESS',
        opensearchServerlessConfiguration: {
          collectionArn: aossCollection.attrArn,
          vectorIndexName,
          fieldMapping: {
            vectorField: 'embedding',
            textField: 'text',
            metadataField: 'metadata',
          },
        },
      },
    });
    // KB creation depends on both the collection and its access policy being ready.
    knowledgeBase.addDependency(aossCollection);
    knowledgeBase.addDependency(accessPolicy);

    // ------------------------------------------------------------------
    // 8. Bedrock Data Source (S3 → Knowledge Base)
    // ------------------------------------------------------------------
    const dataSource = new bedrock.CfnDataSource(this, 'S3DataSource', {
      knowledgeBaseId: knowledgeBase.attrKnowledgeBaseId,
      name: `${slug}-s3-data-source`,
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

    // ------------------------------------------------------------------
    // 9. Stack Outputs
    // ------------------------------------------------------------------
    new CfnOutput(this, 'KnowledgeBaseId', {
      description: 'Bedrock Knowledge Base ID — set as KNOWLEDGE_BASE_ID on the agent runtime',
      value: knowledgeBase.attrKnowledgeBaseId,
      exportName: `${slug}-knowledge-base-id`,
    });

    new CfnOutput(this, 'DataSourceId', {
      description: 'Bedrock Data Source ID — used to trigger KB ingestion sync',
      value: dataSource.attrDataSourceId,
      exportName: `${slug}-data-source-id`,
    });

    new CfnOutput(this, 'S3BucketName', {
      description: 'S3 bucket for BARTT knowledge base documents',
      value: dataBucket.bucketName,
      exportName: `${slug}-kb-bucket-name`,
    });

    new CfnOutput(this, 'AossCollectionEndpoint', {
      description: 'OpenSearch Serverless collection endpoint — needed to create the vector index',
      value: aossCollection.attrCollectionEndpoint,
      exportName: `${slug}-aoss-endpoint`,
    });

    new CfnOutput(this, 'AossCollectionArn', {
      description: 'OpenSearch Serverless collection ARN',
      value: aossCollection.attrArn,
      exportName: `${slug}-aoss-arn`,
    });

    // ------------------------------------------------------------------
    // Expose as class properties (CDK tokens — resolved at deploy time)
    // ------------------------------------------------------------------
    this.knowledgeBaseId = knowledgeBase.attrKnowledgeBaseId;
    this.dataSourceId = dataSource.attrDataSourceId;
    this.s3BucketName = dataBucket.bucketName;
  }
}
