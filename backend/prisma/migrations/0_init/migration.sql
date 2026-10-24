-- CreateEnum
CREATE TYPE "Role" AS ENUM ('OWNER', 'MEMBER');

-- CreateEnum
CREATE TYPE "ApiKeySource" AS ENUM ('WORKSPACE', 'PLATFORM', 'TRIAL_CREDIT', 'WORKSPACE_THEN_PLATFORM');

-- CreateEnum
CREATE TYPE "Source" AS ENUM ('MANUAL', 'API', 'EMAIL', 'WEBHOOK');

-- CreateEnum
CREATE TYPE "ExtractionStatus" AS ENUM ('PENDING', 'PROCESSING', 'SUCCESS', 'NEEDS_REVIEW', 'FAILED', 'UNMATCHED');

-- CreateEnum
CREATE TYPE "WebhookEventType" AS ENUM ('SUCCESS', 'NEEDS_REVIEW', 'FAILED', 'UNMATCHED');

-- CreateTable
CREATE TABLE "Plan" (
    "id" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "slug" TEXT NOT NULL,
    "maxExtractionsPerMonth" INTEGER,
    "maxTemplates" INTEGER,
    "maxWebhooks" INTEGER,
    "maxUsers" INTEGER,
    "priceUsdCents" INTEGER NOT NULL DEFAULT 0,
    "isActive" BOOLEAN NOT NULL DEFAULT true,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "Plan_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Workspace" (
    "id" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "slug" TEXT NOT NULL,
    "apiKey" TEXT NOT NULL,
    "inboundSecret" TEXT NOT NULL,
    "planId" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "geminiApiKey" TEXT,
    "allowPlatformFallback" BOOLEAN NOT NULL DEFAULT false,
    "trialExtractionsRemaining" INTEGER NOT NULL DEFAULT 0,
    "trialGrantedAt" TIMESTAMP(3),

    CONSTRAINT "Workspace_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "User" (
    "id" TEXT NOT NULL,
    "email" TEXT NOT NULL,
    "passwordHash" TEXT,
    "name" TEXT,
    "googleId" TEXT,
    "avatarUrl" TEXT,
    "workspaceId" TEXT NOT NULL,
    "role" "Role" NOT NULL DEFAULT 'MEMBER',
    "isActive" BOOLEAN NOT NULL DEFAULT true,
    "emailVerifiedAt" TIMESTAMP(3),
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "User_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Template" (
    "id" TEXT NOT NULL,
    "workspaceId" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "description" TEXT,
    "schema" JSONB NOT NULL,
    "version" INTEGER NOT NULL DEFAULT 1,
    "isActive" BOOLEAN NOT NULL DEFAULT true,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "Template_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "DocumentLog" (
    "id" TEXT NOT NULL,
    "workspaceId" TEXT NOT NULL,
    "templateId" TEXT,
    "userId" TEXT,
    "source" "Source" NOT NULL,
    "status" "ExtractionStatus" NOT NULL DEFAULT 'PENDING',
    "rawInput" TEXT,
    "rawInputUrl" TEXT,
    "fileName" TEXT,
    "mimeType" TEXT,
    "extractedJson" JSONB,
    "confidenceScores" JSONB,
    "validationErrors" JSONB,
    "processingMs" INTEGER,
    "progress" JSONB,
    "apiKeySource" "ApiKeySource",
    "modelUsed" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "DocumentLog_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "WebhookEndpoint" (
    "id" TEXT NOT NULL,
    "workspaceId" TEXT NOT NULL,
    "url" TEXT NOT NULL,
    "secret" TEXT NOT NULL,
    "description" TEXT,
    "eventTypes" "WebhookEventType"[] DEFAULT ARRAY[]::"WebhookEventType"[],
    "templateIds" TEXT[] DEFAULT ARRAY[]::TEXT[],
    "isActive" BOOLEAN NOT NULL DEFAULT true,
    "lastPingAt" TIMESTAMP(3),
    "failureCount" INTEGER NOT NULL DEFAULT 0,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "WebhookEndpoint_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "WebhookDelivery" (
    "id" TEXT NOT NULL,
    "webhookId" TEXT NOT NULL,
    "documentLogId" TEXT NOT NULL,
    "statusCode" INTEGER,
    "responseBody" TEXT,
    "durationMs" INTEGER,
    "error" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "WebhookDelivery_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "ExtractionCorrection" (
    "id" TEXT NOT NULL,
    "documentLogId" TEXT NOT NULL,
    "templateId" TEXT NOT NULL,
    "originalJson" JSONB NOT NULL,
    "correctedJson" JSONB NOT NULL,
    "templateVersion" INTEGER NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "ExtractionCorrection_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "Plan_slug_key" ON "Plan"("slug");

-- CreateIndex
CREATE UNIQUE INDEX "Workspace_slug_key" ON "Workspace"("slug");

-- CreateIndex
CREATE UNIQUE INDEX "Workspace_apiKey_key" ON "Workspace"("apiKey");

-- CreateIndex
CREATE UNIQUE INDEX "Workspace_inboundSecret_key" ON "Workspace"("inboundSecret");

-- CreateIndex
CREATE INDEX "Workspace_planId_idx" ON "Workspace"("planId");

-- CreateIndex
CREATE UNIQUE INDEX "User_email_key" ON "User"("email");

-- CreateIndex
CREATE UNIQUE INDEX "User_googleId_key" ON "User"("googleId");

-- CreateIndex
CREATE INDEX "User_workspaceId_idx" ON "User"("workspaceId");

-- CreateIndex
CREATE INDEX "Template_workspaceId_idx" ON "Template"("workspaceId");

-- CreateIndex
CREATE INDEX "DocumentLog_workspaceId_idx" ON "DocumentLog"("workspaceId");

-- CreateIndex
CREATE INDEX "DocumentLog_workspaceId_createdAt_idx" ON "DocumentLog"("workspaceId", "createdAt");

-- CreateIndex
CREATE INDEX "DocumentLog_workspaceId_status_idx" ON "DocumentLog"("workspaceId", "status");

-- CreateIndex
CREATE INDEX "DocumentLog_workspaceId_templateId_idx" ON "DocumentLog"("workspaceId", "templateId");

-- CreateIndex
CREATE INDEX "DocumentLog_workspaceId_source_idx" ON "DocumentLog"("workspaceId", "source");

-- CreateIndex
CREATE INDEX "WebhookEndpoint_workspaceId_idx" ON "WebhookEndpoint"("workspaceId");

-- CreateIndex
CREATE INDEX "WebhookDelivery_webhookId_idx" ON "WebhookDelivery"("webhookId");

-- CreateIndex
CREATE INDEX "WebhookDelivery_documentLogId_idx" ON "WebhookDelivery"("documentLogId");

-- CreateIndex
CREATE UNIQUE INDEX "ExtractionCorrection_documentLogId_key" ON "ExtractionCorrection"("documentLogId");

-- CreateIndex
CREATE INDEX "ExtractionCorrection_templateId_idx" ON "ExtractionCorrection"("templateId");

-- CreateIndex
CREATE INDEX "ExtractionCorrection_templateId_templateVersion_idx" ON "ExtractionCorrection"("templateId", "templateVersion");

-- AddForeignKey
ALTER TABLE "Workspace" ADD CONSTRAINT "Workspace_planId_fkey" FOREIGN KEY ("planId") REFERENCES "Plan"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "User" ADD CONSTRAINT "User_workspaceId_fkey" FOREIGN KEY ("workspaceId") REFERENCES "Workspace"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Template" ADD CONSTRAINT "Template_workspaceId_fkey" FOREIGN KEY ("workspaceId") REFERENCES "Workspace"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "DocumentLog" ADD CONSTRAINT "DocumentLog_workspaceId_fkey" FOREIGN KEY ("workspaceId") REFERENCES "Workspace"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "DocumentLog" ADD CONSTRAINT "DocumentLog_templateId_fkey" FOREIGN KEY ("templateId") REFERENCES "Template"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "DocumentLog" ADD CONSTRAINT "DocumentLog_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "WebhookEndpoint" ADD CONSTRAINT "WebhookEndpoint_workspaceId_fkey" FOREIGN KEY ("workspaceId") REFERENCES "Workspace"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "WebhookDelivery" ADD CONSTRAINT "WebhookDelivery_webhookId_fkey" FOREIGN KEY ("webhookId") REFERENCES "WebhookEndpoint"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "WebhookDelivery" ADD CONSTRAINT "WebhookDelivery_documentLogId_fkey" FOREIGN KEY ("documentLogId") REFERENCES "DocumentLog"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ExtractionCorrection" ADD CONSTRAINT "ExtractionCorrection_documentLogId_fkey" FOREIGN KEY ("documentLogId") REFERENCES "DocumentLog"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ExtractionCorrection" ADD CONSTRAINT "ExtractionCorrection_templateId_fkey" FOREIGN KEY ("templateId") REFERENCES "Template"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

