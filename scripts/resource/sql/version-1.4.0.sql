-- LayerToll (OKX Dev Day 2026): agent services, per-tool x402 pricing,
-- X Layer settlement receipts and payment replay protection.
SET FOREIGN_KEY_CHECKS=0;

ALTER TABLE `mcp_service` ADD `agent_published` tinyint NULL DEFAULT 0 COMMENT '1 = exposed on /a2mcp and /agent-mcp';
ALTER TABLE `mcp_service` ADD `payout_wallet` varchar(42) NULL COMMENT 'X Layer address receiving x402 payments';
ALTER TABLE `mcp_tool_api` ADD `x402_price` decimal(18,6) NULL COMMENT 'Per-call x402 price in USD; NULL/0 = free';

CREATE TABLE IF NOT EXISTS `agent_call` (
  `id` char(36) NOT NULL,
  `service_id` char(36) NOT NULL,
  `tool_id` char(36) NULL,
  `tool_name` varchar(255) NOT NULL,
  `transport` varchar(32) NOT NULL COMMENT 'a2mcp_http | mcp',
  `price_usd` decimal(18,6) NULL,
  `payment_status` varchar(32) NOT NULL,
  `payment_error` varchar(255) NULL,
  `replay_key` varchar(255) NULL,
  `payer` varchar(64) NULL,
  `pay_to` varchar(64) NULL,
  `network` varchar(32) NULL,
  `asset` varchar(64) NULL,
  `amount_atomic` varchar(78) NULL,
  `tx_hash` varchar(80) NULL,
  `onchain_verified` tinyint(1) NULL,
  `upstream_status` int NULL,
  `success` tinyint(1) NOT NULL DEFAULT 0,
  `error` text NULL,
  `latency_ms` int NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_agent_call_service` (`service_id`),
  KEY `idx_agent_call_created` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='Agent calls and x402 settlement receipts';

CREATE TABLE IF NOT EXISTS `agent_payment_replay` (
  `replay_key` varchar(255) NOT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`replay_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='Claimed x402 authorizations (replay protection)';

INSERT INTO `sys_config` (`id`,`key`, `value`,`description`,`created_at`,`updated_at`)
VALUES ('xpack-version','version', '1.4.0', 'LayerToll agent services + x402 on X Layer', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    ON DUPLICATE KEY UPDATE `value` = VALUES(`value`), `description` = VALUES(`description`), `updated_at` = CURRENT_TIMESTAMP;

SET FOREIGN_KEY_CHECKS=1;
