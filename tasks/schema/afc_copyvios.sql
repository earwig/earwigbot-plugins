-- MySQL dump 10.13  Distrib 5.5.12, for solaris10 (i386)
--
-- Host: sql    Database: u_earwig_afc_copyvios
-- ------------------------------------------------------
-- Server version       5.1.59

CREATE DATABASE `u_earwig_afc_copyvios`
    DEFAULT CHARACTER SET utf8
    DEFAULT COLLATE utf8_unicode_ci;

--
-- Table structure for table `cache`
--

DROP TABLE IF EXISTS `cache`;
CREATE TABLE `cache` (
    `cache_id` BINARY(32) NOT NULL,
    `cache_time` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `cache_queries` INT(4) NOT NULL DEFAULT 0,
    `cache_process_time` FLOAT NOT NULL DEFAULT 0,
    `cache_possible_miss` BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (`cache_id`)
) ENGINE=InnoDB;

--
-- Table structure for table `cache_data`
--

DROP TABLE IF EXISTS `cache_data`;
CREATE TABLE `cache_data` (
    `cdata_id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `cdata_cache_id` BINARY(32) NOT NULL,
    `cdata_url` VARCHAR(1024) NOT NULL,
    `cdata_confidence` FLOAT NOT NULL DEFAULT 0,
    `cdata_skipped` BOOLEAN NOT NULL DEFAULT 0,
    PRIMARY KEY (`cdata_id`),
    FOREIGN KEY (`cdata_cache_id`)
        REFERENCES `cache` (`cache_id`)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB;

--
-- Table structure for table `processed`
--

DROP TABLE IF EXISTS `processed`;
CREATE TABLE `processed` (
    `page_id` INT(10) UNSIGNED NOT NULL,
    PRIMARY KEY (`page_id`)
) ENGINE=InnoDB;

-- Dump completed on 2014-08-04 20:00:00
