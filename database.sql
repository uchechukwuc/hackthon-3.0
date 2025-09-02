-- database.sql

-- Create a table for users
CREATE TABLE users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(150) NOT NULL UNIQUE,
    password_hash VARCHAR(256) NOT NULL,
    credits INT NOT NULL DEFAULT 0,
    stripe_customer_id VARCHAR(255) UNIQUE
);

-- Modify the existing flashcards table to link to a user
ALTER TABLE flashcards ADD COLUMN user_id INT;

ALTER TABLE flashcards ADD CONSTRAINT fk_user
FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;