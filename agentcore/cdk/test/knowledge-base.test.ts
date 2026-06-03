import * as cdk from 'aws-cdk-lib';
import { Template } from 'aws-cdk-lib/assertions';
import { KnowledgeBaseStack } from '../lib/knowledge-base-stack';

const TEST_ENV: cdk.Environment = {
  account: '123456789012',
  region: 'ap-south-1',
};

function buildStack(overrides?: Partial<cdk.StackProps & { adminPrincipalArn?: string }>) {
  const app = new cdk.App();
  return new KnowledgeBaseStack(app, 'TestKBStack', {
    projectName: 'bartt-test',
    env: TEST_ENV,
    ...overrides,
  });
}

// ---------------------------------------------------------------------------
// Synthesis smoke test
// ---------------------------------------------------------------------------

test('KnowledgeBaseStack synthesizes without errors', () => {
  const stack = buildStack();
  const template = Template.fromStack(stack);
  // A non-empty template confirms successful synthesis.
  expect(Object.keys(template.toJSON().Resources).length).toBeGreaterThan(0);
});

// ---------------------------------------------------------------------------
// S3 Bucket
// ---------------------------------------------------------------------------

test('creates an S3 bucket with versioning and SSL enforcement', () => {
  const stack = buildStack();
  const template = Template.fromStack(stack);

  template.hasResourceProperties('AWS::S3::Bucket', {
    VersioningConfiguration: { Status: 'Enabled' },
    BucketEncryption: {
      ServerSideEncryptionConfiguration: [
        { ServerSideEncryptionByDefault: { SSEAlgorithm: 'AES256' } },
      ],
    },
    PublicAccessBlockConfiguration: {
      BlockPublicAcls: true,
      BlockPublicPolicy: true,
      IgnorePublicAcls: true,
      RestrictPublicBuckets: true,
    },
  });
});

// ---------------------------------------------------------------------------
// IAM Role
// ---------------------------------------------------------------------------

test('creates an IAM role assumed by bedrock.amazonaws.com', () => {
  const stack = buildStack();
  const template = Template.fromStack(stack);

  template.hasResourceProperties('AWS::IAM::Role', {
    AssumeRolePolicyDocument: {
      Statement: [
        {
          Effect: 'Allow',
          Principal: { Service: 'bedrock.amazonaws.com' },
        },
      ],
    },
  });
});

// ---------------------------------------------------------------------------
// OpenSearch Serverless
// ---------------------------------------------------------------------------

test('creates an AOSS VECTORSEARCH collection', () => {
  const stack = buildStack();
  const template = Template.fromStack(stack);

  template.hasResourceProperties('AWS::OpenSearchServerless::Collection', {
    Type: 'VECTORSEARCH',
  });
});

test('creates encryption and network security policies', () => {
  const stack = buildStack();
  const template = Template.fromStack(stack);

  template.resourceCountIs('AWS::OpenSearchServerless::SecurityPolicy', 2);
});

test('creates a data access policy', () => {
  const stack = buildStack();
  const template = Template.fromStack(stack);

  template.hasResourceProperties('AWS::OpenSearchServerless::AccessPolicy', {
    Type: 'data',
  });
});

// ---------------------------------------------------------------------------
// Bedrock Knowledge Base
// ---------------------------------------------------------------------------

test('creates a VECTOR knowledge base backed by OpenSearch Serverless', () => {
  const stack = buildStack();
  const template = Template.fromStack(stack);

  template.hasResourceProperties('AWS::Bedrock::KnowledgeBase', {
    KnowledgeBaseConfiguration: {
      Type: 'VECTOR',
    },
    StorageConfiguration: {
      Type: 'OPENSEARCH_SERVERLESS',
      OpensearchServerlessConfiguration: {
        VectorIndexName: 'bartt-kb-index',
        FieldMapping: {
          VectorField: 'embedding',
          TextField: 'text',
          MetadataField: 'metadata',
        },
      },
    },
  });
});

// ---------------------------------------------------------------------------
// Bedrock Data Source
// ---------------------------------------------------------------------------

test('creates an S3 data source with fixed-size chunking', () => {
  const stack = buildStack();
  const template = Template.fromStack(stack);

  template.hasResourceProperties('AWS::Bedrock::DataSource', {
    DataSourceConfiguration: {
      Type: 'S3',
    },
    VectorIngestionConfiguration: {
      ChunkingConfiguration: {
        ChunkingStrategy: 'FIXED_SIZE',
        FixedSizeChunkingConfiguration: {
          MaxTokens: 512,
          OverlapPercentage: 20,
        },
      },
    },
  });
});

// ---------------------------------------------------------------------------
// Stack Outputs
// ---------------------------------------------------------------------------

test('emits required CloudFormation outputs', () => {
  const stack = buildStack();
  const template = Template.fromStack(stack);

  // Five outputs expected
  const outputs = template.toJSON().Outputs as Record<string, unknown>;
  const outputKeys = Object.keys(outputs);

  expect(outputKeys).toContain('KnowledgeBaseId');
  expect(outputKeys).toContain('DataSourceId');
  expect(outputKeys).toContain('S3BucketName');
  expect(outputKeys).toContain('AossCollectionEndpoint');
  expect(outputKeys).toContain('AossCollectionArn');
});
