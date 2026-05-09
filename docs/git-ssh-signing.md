# SSH commit signing with Git

Git can sign commits and tags with an **SSH key** instead of GPG. That gives you a **Verified** badge on GitHub when the signing key is registered on your account, and it reuses the same style of keys many people already use for `git@github.com:…` pushes.

## Requirements

- **Git 2.34+** (`git --version`) for `gpg.format ssh`.
- **GitHub:** add the key as a **Signing key** (not only as an authentication key). See GitHub’s [SSH commit signature verification](https://docs.github.com/en/authentication/managing-commit-signature-verification/about-commit-signature-verification#ssh-commit-signatures).

## One-time setup

1. **Use or create an SSH key** (Ed25519 is a good default):

   ```bash
   ssh-keygen -t ed25519 -C "your_email@example.com" -f ~/.ssh/id_ed25519_git_signing
   ```

   Or reuse an existing key whose **public** `.pub` file you are comfortable registering as a signing key.

2. **Upload the public key to GitHub**  
   **Settings → SSH and GPG keys → New SSH key** → key type **Signing Key** → paste the contents of `*.pub`.

3. **Tell Git to sign with SSH** (paths are examples — use your real `.pub` path):

   ```bash
   git config --global gpg.format ssh
   git config --global user.signingkey ~/.ssh/id_ed25519_git_signing.pub
   git config --global commit.gpgsign true
   ```

   Optional — sign tags by default:

   ```bash
   git config --global tag.gpgsign true
   ```

4. **Optional: sign only in this repo**  
   Run the same `git config` commands **without** `--global` from the repository root so they are stored in `.git/config`.

## Check that it works

Make a commit and inspect the signature:

```bash
git commit --allow-empty -m "test: ssh signing"
git log -1 --show-signature
```

On GitHub, the commit should show as **Verified** if the signing key matches your account.

## Troubleshooting

- **`error: gpg.ssh.unknown_key_reason` / unverified**  
  Confirm the key is added as a **Signing** key on GitHub and that `user.signingkey` points at the correct **public** key file.

- **`secret key not available`**  
  Git must be able to use the private key (file permissions, or your SSH agent / 1Password / etc., depending on how you store keys). The `user.signingkey` value is still the **public** key path; Git uses it to pick the matching private key.

- **CI / bots**  
  Commit signing is a **developer machine** (or release pipeline) setting; it is not enabled by anything in this repository alone. Enforcing signed commits on a branch is done in **GitHub branch protection** (organization/repo settings), not in these docs.

## Further reading

- [Telling Git about your signing key](https://docs.github.com/en/authentication/managing-commit-signature-verification/telling-git-about-your-signing-key) (SSH)
- Git book: [Signing commits with SSH keys](https://git-scm.com/book/en/v2/Git-Tools-Signing-Your-Work#_signing_commits_with_ssh_keys)
