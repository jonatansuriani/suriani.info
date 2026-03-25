# Jekyll + github-pages (Ruby aligned with .ruby-version and GitHub Actions)
FROM ruby:3.3.6-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv/jekyll

ENV BUNDLE_SILENCE_ROOT_WARNING=1 \
    BUNDLE_FROZEN=0 \
    JEKYLL_ENV=production

# Cache gems unless Gemfile / lock change
COPY Gemfile Gemfile.lock ./
RUN bundle install

COPY . .

# Default: production build into /srv/jekyll/_site
#
# Local preview (simplest): docker compose up --build  → http://localhost:4000
#
# One-off build with live files: docker compose run --rm site bundle exec jekyll build
#
# Without Compose: docker build -t suriani-jekyll:local . && docker run --rm -p 4000:4000 \
#   -v "$PWD:/srv/jekyll" suriani-jekyll:local bundle exec jekyll serve --host 0.0.0.0
CMD ["bundle", "exec", "jekyll", "build", "--trace"]
